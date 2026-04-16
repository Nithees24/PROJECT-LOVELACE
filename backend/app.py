from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from backend.llm.llm_client import LLMClient
from backend.agents.general_chat_agent import GeneralChatAgent
from backend.agents.deep_research_agent import DeepResearchAgent
from backend.pipeline.planner import Planner
from backend.database.connection import create_tables
from backend.database import message_model
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
