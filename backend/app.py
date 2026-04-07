from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from backend.llm.llm_client import LLMClient
from backend.agents.general_chat_agent import GeneralChatAgent
from backend.agents.deep_research_agent import DeepResearchAgent
from backend.pipeline.planner import Planner
from backend.database.connection import create_tables
from backend.database import message_model
from backend.database.connection import SessionLocal
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
