from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

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

from datetime import datetime

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
def register(req: SignupRequest):
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

        new_user = User(
            email=req.email,
            password_hash=hash_password(req.password),
            first_name=req.first_name,
            last_name=req.last_name,
            role=req.role,
            age=calculated_age,
            dob=req.dob,
            gender=req.gender
        )
        db.add(new_user)
        db.commit()
        return {"success": True, "message": "User created successfully"}
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
        conversations = db.query(Conversation).filter(Conversation.user_id == user_id).order_by(Conversation.created_at.desc()).all()
        return {
            "success": True, 
            "conversations": [
                {"id": c.id, "title": c.title, "created_at": c.created_at.isoformat()} for c in conversations
            ]
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

def generate_thread_title(first_prompt: str):
    try:
        # Simple concise prompt for title generation
        prompt = f"Summarize the following user request into a very concise 2-4 word title for a chat thread. Return ONLY the title text, no quotes or punctuation: {first_prompt}"
        title = llm_client.generate(prompt, model=CHAT_MODEL)
        return title.strip()
    except:
        # Fallback to snippet if LLM fails
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
def delete_conversation(conversation_id: int):
    db = SessionLocal()
    try:
        conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if not conv:
            return {"error": "Conversation not found"}
        db.delete(conv)
        db.commit()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
    finally:
        db.close()

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

        # 🔬 Deep Research → stateless
        if req.mode == "Deep Research":
            reply = deep_agent.run(req.message)

        # 🧠 General Chat → stateful
        else:
            history = get_conversation_history(db, req.conversation_id)

            reply = general_agent.run_with_history(
                req.message,
                history
            )

        # 🔹 Save assistant reply
        save_message(db, req.conversation_id, "assistant", reply)

        return {"reply": reply}

    except Exception as e:
        return {"error": str(e)}

    finally:
        db.close()
