import sys
import os

# Ensure the root project directory is in sys.path so 'backend' is recognized as a module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, BackgroundTasks

from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uuid
from backend.utils.email_utils import send_verification_email
from backend.config import BASE_URL

from backend.llm.llm_client import LLMClient
from backend.agents.general_chat_agent import GeneralChatAgent
from backend.agents.deep_research_agent import DeepResearchAgent
from backend.pipeline.planner import Planner
from backend.database.connection import create_tables
from backend.database import message_model
from backend.database import conversation_model
from backend.database.user_model import User
from backend.database.connection import SessionLocal
import hashlib
from backend.database.message_repo import save_message, get_messages
from backend.config import CHAT_MODEL
from fastapi import File, UploadFile
from backend.rag.pdf_utils import extract_text_from_file, chunk_text
from backend.rag.vector_store import VectorStore
import shutil
import os

def get_conversation_history(db, conversation_id):
    messages = get_messages(db, conversation_id)
    history = [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]
    return history[-20:]
app = FastAPI()

create_tables()

# ✅ Enable CORS (frontend can call backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Initialize once
llm_client = LLMClient()
general_agent = GeneralChatAgent(llm_client)
deep_agent = DeepResearchAgent(llm_client)
planner = Planner(llm_client)

from datetime import datetime, timedelta

class CheckEmailRequest(BaseModel):
    email: str

class LoginRequest(BaseModel):
    email: str
    password: str

class SignupRequest(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    role: str
    dob: str = None
    gender: str = None

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

@app.post("/api/auth/check-email")
def check_email(req: CheckEmailRequest):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == req.email).first()
        return {"exists": user is not None}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

@app.post("/api/auth/register")
def register(req: SignupRequest, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        exists = db.query(User).filter(User.email == req.email).first()
        if exists:
            return {"error": "Email already registered"}
        
        # Calculate age if dob is provided
        calculated_age = None
        if req.dob:
            try:
                dob_date = datetime.strptime(req.dob, "%Y-%m-%d")
                today = datetime.utcnow()
                calculated_age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
            except ValueError:
                pass # Fallback if date is invalid

        verification_token = str(uuid.uuid4())

        new_user = User(
            email=req.email,
            password_hash=hash_password(req.password),
            first_name=req.first_name,
            last_name=req.last_name,
            role=req.role,
            age=calculated_age,
            dob=req.dob,
            gender=req.gender,
            verification_token=verification_token
        )
        db.add(new_user)
        db.commit()

        background_tasks.add_task(
            send_verification_email,
            req.email,
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
    email: str

@app.post("/api/auth/resend-email")
def resend_email(req: ResendEmailRequest, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == req.email).first()
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
        user = db.query(User).filter(User.email == req.email).first()
        if not user:
            return {"error": "User not found"}
        
        if user.password_hash != hash_password(req.password):
            return {"error": "Incorrect password"}
            
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
            user.dob = req.dob
            try:
                dob_date = datetime.strptime(req.dob, "%Y-%m-%d")
                today = datetime.utcnow()
                user.age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
            except ValueError:
                pass
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

from backend.database.conversation_model import Conversation

class CreateConversationRequest(BaseModel):
    user_id: int

@app.post("/api/conversations")
def create_conversation(req: CreateConversationRequest):
    db = SessionLocal()
    try:
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
    print(f"DEBUG: Rating conversation {conversation_id} with score {req.score}")
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
        print(f"Failed to generate title: {e}")
        return first_prompt[:30] + "..." if len(first_prompt) > 30 else first_prompt

@app.get("/api/messages/{conversation_id}")
def get_conversation_messages_endpoint(conversation_id: int):
    db = SessionLocal()
    try:
        messages = get_messages(db, conversation_id)
        return {
            "success": True,
            "messages": [
                {"role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()} for m in messages
            ]
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
        
        from backend.database.message_model import Message
        db.query(Message).filter(Message.conversation_id == conversation_id).delete()
        
        db.delete(conv)
        db.commit()

        # Delete RAG data if exists
        rag_path = f"backend/rag/rag_state/{conversation_id}.marker"
        if os.path.exists(rag_path):
            os.remove(rag_path)
            # Delete the corresponding namespace in Pinecone in the background
            from backend.rag.vector_store import VectorStore
            def remove_namespace():
                try:
                    store = VectorStore()
                    store.delete_namespace(conversation_id)
                except Exception as e:
                    print(f"Background task failed to delete namespace: {e}")
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
        temp_path = f"backend/data/rag/temp_{file.filename}"
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Extract and chunk
        print(f"Extracting text from {temp_path}...")
        text = extract_text_from_file(temp_path)
        print(f"Extracted {len(text)} characters. Chunking...")
        chunks = chunk_text(text)
        
        # Add chunks to Pinecone
        print(f"Indexing {len(chunks)} chunks for conversation {conversation_id}...")
        store = VectorStore()
        store.add_chunks(chunks, conversation_id)
        print("Indexing complete.")
        
        # Persist the upload action in the chat history
        db = SessionLocal()
        try:
            save_message(db, conversation_id, "user", f"Uploaded file: {file.filename}")
        except Exception as e:
            print(f"Failed to save upload message: {e}")
        finally:
            db.close()
        
        # We still create a small marker file to know RAG is enabled for this conv
        marker_dir = "backend/rag/rag_state"
        os.makedirs(marker_dir, exist_ok=True)
        rag_marker = f"{marker_dir}/{conversation_id}.marker"
        with open(rag_marker, "w") as f:
            f.write("rag_enabled")
        
        # Clean up temp file
        os.remove(temp_path)
        
        return {"success": True, "message": f"Successfully indexed {len(chunks)} chunks in Pinecone for conversation {conversation_id}"}
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"UPLOAD ERROR: {error_details}")
        return {"error": str(e)}

class ChatRequest(BaseModel):
    message: str
    conversation_id: int
    mode: str = "Chat Agent"
    messages: list = []

# ✅ API endpoint
@app.post("/api/chat")
def chat(req: ChatRequest):
    db = SessionLocal()

    try:
        # 🔹 Smart Title Update: If it's a new conversation, title it based on the first prompt
        conv = db.query(Conversation).filter(Conversation.id == req.conversation_id).first()
        if conv and conv.title == "New Conversation":
            conv.title = generate_thread_title(req.message)
            db.commit()

        # 🔹 Save user message
        save_message(db, req.conversation_id, "user", req.message)

        # 🔹 Check for RAG context
        rag_context = ""
        rag_marker = f"backend/rag/rag_state/{req.conversation_id}.marker"
        if os.path.exists(rag_marker):
            store = VectorStore()
            results = store.search(req.message, req.conversation_id, top_k=3)
            if results:
                rag_context = "\n\nContext from uploaded documents:\n" + "\n".join([r["chunk"] for r in results])

        # 🔬 Deep Research → stateless
        if req.mode == "Deep Research":
            reply = deep_agent.run(req.message + rag_context)
            sources = []

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

        # 🔹 Save assistant reply
        save_message(db, req.conversation_id, "assistant", reply)

        return {"reply": reply, "sources": sources}

    except Exception as e:
        return {"error": str(e)}

    finally:
        db.close()

class AbortMessageRequest(BaseModel):
    conversation_id: str
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
