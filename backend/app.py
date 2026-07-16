import sys
import os
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure the root project directory is in sys.path so 'backend' is recognized as a module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Anchor all filesystem paths to the repo root (like logger.py does) so the
# server works regardless of the CWD it was launched from (BUG-14)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAG_STATE_DIR = PROJECT_ROOT / "backend" / "rag" / "rag_state"
RAG_TEMP_DIR = PROJECT_ROOT / "backend" / "data" / "rag"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

import hashlib
import shutil
import time
import traceback
import uuid
from datetime import datetime, timedelta

from fastapi import FastAPI, BackgroundTasks, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
from sqlalchemy import func

from backend.utils.logger import logger
from backend.utils.email_utils import send_verification_email
from backend.config import BASE_URL, CHAT_MODEL, RAG_SCORE_THRESHOLD, PRODUCTION
from backend.llm.llm_client import LLMClient
from backend.agents.general_chat_agent import GeneralChatAgent
from backend.agents.deep_research_agent import DeepResearchAgent
from backend.pipeline.planner import Planner
from backend.database.connection import create_tables, SessionLocal
from backend.database.user_model import User
from backend.database.conversation_model import Conversation
from backend.database.message_model import Message
from backend.database.message_repo import save_message, get_messages, get_conversation_history
from backend.rag.pdf_utils import extract_text_from_file, chunk_text
from backend.rag.vector_store import VectorStore

# Globals populated by the lifespan handler at startup (BUG-17). Importing
# this module is side-effect-free: no DB connection, no LLM client work.
llm_client = None
general_agent = None
deep_agent = None
planner = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global llm_client, general_agent, deep_agent, planner
    create_tables()
    llm_client = LLMClient()
    llm_client.probe()  # fail loudly at boot on a bad model name (BUG-02)
    general_agent = GeneralChatAgent(llm_client)
    deep_agent = DeepResearchAgent(llm_client)
    planner = Planner(llm_client)
    logger.info("Startup complete: database ready, agents initialized.")
    yield

app = FastAPI(lifespan=lifespan)

# ✅ Enable CORS (frontend can call backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    client_host = request.client.host if request.client else "unknown"
    logger.info(f"Incoming request: {request.method} {request.url.path} from client {client_host}")
    
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        logger.info(f"Completed request: {request.method} {request.url.path} - Status: {response.status_code} - Processed in {process_time:.2f}ms")
        return response
    except Exception as e:
        process_time = (time.time() - start_time) * 1000
        logger.error(f"Request failed: {request.method} {request.url.path} - Error: {str(e)} - Processed in {process_time:.2f}ms", exc_info=True)
        raise e

class CheckEmailRequest(BaseModel):
    email: EmailStr

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    role: str
    dob: str = None
    gender: str = None

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def normalize_email(email: str) -> str:
    """Lowercase so A@x.com and a@x.com can't become two accounts (BUG-26)."""
    return email.strip().lower()

def parse_dob(dob_str: str):
    """Strictly validate a YYYY-MM-DD date of birth (BUG-27).

    Returns (normalized_dob_string, age). Raises ValueError for impossible
    calendar dates (e.g. 2000-02-31) or dates in the future."""
    dob_date = datetime.strptime(dob_str.strip(), "%Y-%m-%d")
    today = datetime.utcnow()
    if dob_date > today:
        raise ValueError("date of birth is in the future")
    age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
    return dob_date.strftime("%Y-%m-%d"), age

INVALID_DOB_ERROR = "Invalid date of birth: please enter a real calendar date (YYYY-MM-DD) that is not in the future."

def find_user_by_email(db, email: str):
    """Case-insensitive lookup — tolerates mixed-case emails stored before
    normalization was introduced."""
    return db.query(User).filter(func.lower(User.email) == normalize_email(email)).first()

@app.post("/api/auth/check-email")
def check_email(req: CheckEmailRequest):
    db = SessionLocal()
    try:
        user = find_user_by_email(db, req.email)
        return {"exists": user is not None}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.post("/api/auth/register")
def register(req: SignupRequest, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        email = normalize_email(req.email)
        exists = find_user_by_email(db, email)
        if exists:
            return {"error": "Email already registered"}
        
        # Validate dob strictly — reject impossible dates instead of silently
        # storing them with a NULL age (BUG-27)
        dob = None
        calculated_age = None
        if req.dob:
            try:
                dob, calculated_age = parse_dob(req.dob)
            except ValueError:
                return {"error": INVALID_DOB_ERROR}

        verification_token = str(uuid.uuid4())

        new_user = User(
            email=email,
            password_hash=hash_password(req.password),
            first_name=req.first_name,
            last_name=req.last_name,
            role=req.role,
            age=calculated_age,
            dob=dob,
            gender=req.gender,
            verification_token=verification_token
        )
        db.add(new_user)
        db.commit()

        background_tasks.add_task(
            send_verification_email,
            email,
            verification_token,
            BASE_URL
        )

        return {"success": True, "message": "User created successfully"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.get("/api/auth/verify/{token}", response_class=HTMLResponse)
def verify_email(token: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.verification_token == token).first()
        if not user:
            return HTMLResponse(content="""
                <html>
                    <body style="background-color:#182321; color:#fff; font-family:sans-serif; text-align:center; padding-top:100px;">
                        <h2>Verification Failed</h2>
                        <p style="color:#ff8d72;">Invalid or expired verification link.</p>
                    </body>
                </html>
            """, status_code=404)
        
        user.is_verified = True
        user.verification_token = None
        db.commit()
        
        return HTMLResponse(content="""
            <html>
                <body style="background-color:#182321; color:#fff; font-family:sans-serif; text-align:center; padding-top:100px;">
                    <h2>Email Verified Successfully!</h2>
                    <p style="color:#34A853;">Your research identity has been confirmed. You can close this tab and return to the login page.</p>
                </body>
            </html>
        """)
    except Exception as e:
        return HTMLResponse(content=f"Error: {str(e)}", status_code=500)
    finally:
        db.close()

class ResendEmailRequest(BaseModel):
    email: EmailStr

@app.post("/api/auth/resend-email")
def resend_email(req: ResendEmailRequest, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        user = find_user_by_email(db, req.email)
        if not user:
            return {"error": "User not found"}
        if user.is_verified:
            return {"error": "User is already verified"}
            
        now = datetime.utcnow()
        current_count = user.resend_count or 0
        
        if current_count >= 3:
            if user.last_resend_time and now - user.last_resend_time < timedelta(hours=6):
                return {"error": "max no.of time used, try after some time."}
            else:
                user.resend_count = 1
                user.last_resend_time = now
        else:
            if user.last_resend_time and now - user.last_resend_time > timedelta(hours=24):
                user.resend_count = 1
            else:
                user.resend_count = current_count + 1
            user.last_resend_time = now
            
        if not user.verification_token:
            user.verification_token = str(uuid.uuid4())
            
        db.commit()
        
        background_tasks.add_task(
            send_verification_email,
            user.email,
            user.verification_token,
            BASE_URL
        )
        
        return {"success": True, "message": "Verification email resent"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.post("/api/auth/login")
def login(req: LoginRequest):
    db = SessionLocal()
    try:
        user = find_user_by_email(db, req.email)
        if not user:
            return {"error": "User not found"}
        
        if user.password_hash != hash_password(req.password):
            return {"error": "Incorrect password"}
            
        if not user.is_verified:
            return {"error": "Please verify your email address before logging in."}
            
        return {"success": True, "user_id": user.id, "first_name": user.first_name}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

class UpdateProfileRequest(BaseModel):
    user_id: int
    password: str
    first_name: str = None
    last_name: str = None
    dob: str = None
    gender: str = None

class ChangePasswordRequest(BaseModel):
    user_id: int
    current_password: str
    new_password: str

@app.get("/api/auth/profile/{user_id}")
def get_profile(user_id: int):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "User not found"}
        return {
            "success": True,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "dob": user.dob,
            "gender": user.gender,
            "role": user.role
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.put("/api/auth/profile")
def update_profile(req: UpdateProfileRequest):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == req.user_id).first()
        if not user:
            return {"error": "User not found"}
        if user.password_hash != hash_password(req.password):
            return {"error": "Incorrect password"}

        if req.first_name is not None:
            user.first_name = req.first_name
        if req.last_name is not None:
            user.last_name = req.last_name
        if req.dob is not None:
            try:
                user.dob, user.age = parse_dob(req.dob)
            except ValueError:
                return {"error": INVALID_DOB_ERROR}
        if req.gender is not None:
            user.gender = req.gender

        db.commit()
        return {"success": True, "first_name": user.first_name}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.put("/api/auth/change-password")
def change_password(req: ChangePasswordRequest):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == req.user_id).first()
        if not user:
            return {"error": "User not found"}
        if user.password_hash != hash_password(req.current_password):
            return {"error": "Current password is incorrect"}
        if len(req.new_password) < 6:
            return {"error": "New password must be at least 6 characters"}

        user.password_hash = hash_password(req.new_password)
        db.commit()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

class CreateConversationRequest(BaseModel):
    user_id: int

@app.post("/api/conversations")
def create_conversation(req: CreateConversationRequest):
    db = SessionLocal()
    try:
        # Second line of defence on top of the DB foreign key (BUG-25)
        user = db.query(User).filter(User.id == req.user_id).first()
        if not user:
            return {"error": "User not found"}

        new_conv = Conversation(user_id=req.user_id, title="New Conversation")
        db.add(new_conv)
        db.commit()
        db.refresh(new_conv)
        return {"success": True, "conversation_id": new_conv.id, "title": new_conv.title}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.get("/api/conversations/{user_id}")
def get_user_conversations(user_id: int):
    db = SessionLocal()
    try:
        conversations = db.query(Conversation).filter(
            Conversation.user_id == user_id
        ).order_by(
            Conversation.is_pinned.desc(),
            Conversation.pinned_at.desc().nullslast(),
            Conversation.created_at.desc()
        ).all()
        return {
            "success": True, 
            "conversations": [
                {
                    "id": c.id,
                    "title": c.title,
                    "created_at": c.created_at.isoformat(),
                    "is_pinned": c.is_pinned
                } for c in conversations
            ]
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.post("/api/conversations/{conversation_id}/pin")
def toggle_pin_conversation(conversation_id: int):
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            return {"error": "Conversation not found"}
        conv.is_pinned = not conv.is_pinned
        conv.pinned_at = datetime.utcnow() if conv.is_pinned else None
        db.commit()
        return {"success": True, "is_pinned": conv.is_pinned}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

class RateConversationRequest(BaseModel):
    score: int # +1 or -1

@app.post("/api/conversations/{conversation_id}/rate")
def rate_conversation(conversation_id: int, req: RateConversationRequest):
    logger.info(f"Rating conversation {conversation_id} with score {req.score}")
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            return {"error": "Conversation not found"}
        # Increment/Decrement the rating
        conv.rating = (conv.rating or 0) + req.score
        db.commit()
        return {"success": True, "new_rating": conv.rating}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

def generate_thread_title(first_prompt: str):
    try:
        # Generate an expressive and unique title
        prompt = f"Create a concise, unique, and highly descriptive 3-6 word title for a chat thread starting with this user request. Avoid generic starting words like 'Understanding', 'Exploring', or 'A Guide to'. Tailor the title specifically to the topic. Return ONLY the title text, no quotes or punctuation: {first_prompt}"
        title = llm_client.generate(prompt, model=CHAT_MODEL)
        # Remove quotes if the LLM adds them anyway
        title = title.strip().strip('\"\'')
        return title
    except Exception as e:
        # Fallback to snippet if LLM fails
        logger.error(f"Failed to generate title: {e}", exc_info=True)
        return first_prompt[:30] + "..." if len(first_prompt) > 30 else first_prompt

@app.get("/api/messages/{conversation_id}")
def get_conversation_messages_endpoint(conversation_id: int):
    db = SessionLocal()
    try:
        messages = get_messages(db, conversation_id)
        result = []
        for m in messages:
            msg_data = {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat()
            }
            if m.sources:
                try:
                    msg_data["sources"] = json.loads(m.sources)
                except (json.JSONDecodeError, TypeError):
                    msg_data["sources"] = []
            else:
                msg_data["sources"] = []
            result.append(msg_data)
        return {
            "success": True,
            "messages": result
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

class RenameConversationRequest(BaseModel):
    title: str

@app.patch("/api/conversations/{conversation_id}")
def rename_conversation(conversation_id: int, req: RenameConversationRequest):
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            return {"error": "Conversation not found"}
        conv.title = req.title
        db.commit()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            return {"error": "Conversation not found"}
        
        db.query(Message).filter(Message.conversation_id == conversation_id).delete()
        
        db.delete(conv)
        db.commit()

        # Delete RAG data if exists
        rag_path = RAG_STATE_DIR / f"{conversation_id}.marker"
        if rag_path.exists():
            rag_path.unlink()
            # Delete the corresponding namespace in Pinecone in the background
            def remove_namespace():
                try:
                    store = VectorStore()
                    store.delete_namespace(conversation_id)
                except Exception as e:
                    logger.error(f"Background task failed to delete namespace: {e}", exc_info=True)
            background_tasks.add_task(remove_namespace)

        return {"success": True}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()

@app.post("/api/rag/upload")
async def upload_document(conversation_id: int, file: UploadFile = File(...)):
    try:
        # Create temp path for uploaded file
        temp_path = RAG_TEMP_DIR / f"temp_{file.filename}"
        RAG_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Extract and chunk
        logger.info(f"Extracting text from {temp_path}...")
        text = extract_text_from_file(str(temp_path))
        logger.info(f"Extracted {len(text)} characters. Chunking...")
        chunks = chunk_text(text)
        
        # Add chunks to Pinecone
        logger.info(f"Indexing {len(chunks)} chunks for conversation {conversation_id}...")
        store = VectorStore()
        store.add_chunks(chunks, conversation_id)
        logger.info("Indexing complete.")
        
        # Persist the upload action in the chat history
        db = SessionLocal()
        try:
            save_message(db, conversation_id, "user", f"Uploaded file: {file.filename}")
        except Exception as e:
            logger.error(f"Failed to save upload message: {e}", exc_info=True)
        finally:
            db.close()
        
        # We still create a small marker file to know RAG is enabled for this conv
        RAG_STATE_DIR.mkdir(parents=True, exist_ok=True)
        rag_marker = RAG_STATE_DIR / f"{conversation_id}.marker"
        rag_marker.write_text("rag_enabled")

        # Clean up temp file
        temp_path.unlink()
        
        return {"success": True, "message": f"Successfully indexed {len(chunks)} chunks in Pinecone for conversation {conversation_id}"}
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"UPLOAD ERROR: {error_details}")
        return {"error": str(e)}

class ChatRequest(BaseModel):
    message: str
    conversation_id: int
    mode: str = "Chat Agent"
    # NOTE: conversation history is intentionally NOT accepted from the
    # client — it is rebuilt server-side from the database (BUG-12)

# ✅ API endpoint
@app.post("/api/chat")
def chat(req: ChatRequest):
    db = SessionLocal()

    try:
        # 🔹 Smart Title Update: If it's a new conversation, generate the title
        # in PARALLEL with the main answer instead of as a blocking LLM call
        # on the request path (BUG-03). Joined before returning so the
        # frontend's post-reply conversation refresh sees the final title.
        title_thread = None
        title_result = {}
        conv = db.query(Conversation).filter(Conversation.id == req.conversation_id).first()
        if conv and conv.title == "New Conversation":
            def _gen_title(message=req.message):
                title_result["title"] = generate_thread_title(message)
            title_thread = threading.Thread(target=_gen_title, daemon=True)
            title_thread.start()

        # 🔹 Save user message
        save_message(db, req.conversation_id, "user", req.message)

        # 🔹 Check for RAG context
        rag_context = ""
        rag_marker = RAG_STATE_DIR / f"{req.conversation_id}.marker"
        if rag_marker.exists():
            store = VectorStore()
            results = store.search(req.message, req.conversation_id, top_k=3)
            # Only inject chunks that are actually similar to the question;
            # top-k alone returns the nearest chunks even when the question
            # is unrelated to the uploaded document (BUG-13)
            relevant = [r for r in results if r["score"] >= RAG_SCORE_THRESHOLD]
            if results:
                logger.info(
                    f"[RAG] conv {req.conversation_id}: scores="
                    f"{[round(r['score'], 3) for r in results]} "
                    f"threshold={RAG_SCORE_THRESHOLD} kept={len(relevant)}"
                )
            if relevant:
                rag_context = "\n\nContext from uploaded documents:\n" + "\n".join([r["chunk"] for r in relevant])

        # 🔬 Deep Research → stateless
        if req.mode == "Deep Research":
            reply, sources = deep_agent.run(req.message + rag_context)

        # 🧠 General Chat → stateful
        else:
            history = get_conversation_history(db, req.conversation_id)
            
            prompt_with_context = req.message
            if rag_context:
                prompt_with_context = f"CONTEXT FROM UPLOADED DOCUMENTS:\n{rag_context}\n\nUSER QUESTION: {req.message}"

            reply, sources = general_agent.run_with_history(
                prompt_with_context,
                history
            )

        # 🔹 Save assistant reply (with sources as JSON)
        sources_json = json.dumps(sources) if sources else None
        save_message(db, req.conversation_id, "assistant", reply, sources=sources_json)

        # 🔹 Commit the title generated in parallel (finishes well before the
        # main answer, so this join is effectively free)
        if title_thread:
            title_thread.join()
            new_title = title_result.get("title")
            if new_title:
                conv.title = new_title
                db.commit()

        return {"reply": reply, "sources": sources, "model": CHAT_MODEL}

    except Exception as e:
        return {"error": str(e)}

    finally:
        db.close()

class AbortMessageRequest(BaseModel):
    conversation_id: int
    message: str

@app.post("/api/chat/save_aborted")
def save_aborted_message(req: AbortMessageRequest):
    db = SessionLocal()
    try:
        save_message(db, req.conversation_id, "assistant", req.message)
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.get("/")
def read_root():
    return RedirectResponse(url="/login.html")

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

if __name__ == "__main__":
    import uvicorn
    # PRODUCTION=true in .env disables the auto-reloader (BUG-15)
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=not PRODUCTION)

