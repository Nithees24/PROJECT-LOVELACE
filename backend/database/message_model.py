from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from datetime import datetime

from backend.database.connection import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)

    role = Column(String, nullable=False)  # "user" or "assistant"

    content = Column(Text, nullable=False)

    sources = Column(Text, nullable=True)  # JSON-serialized list of search sources

    # JSON-serialized deep-research trace (plan + activity events) so a
    # streamed research run can be replayed when the conversation is reopened.
    research_trace = Column(Text, nullable=True)

    # JSON-serialized document-agent trace ({brief, events}) — the interview
    # Q&A plus streamed activity, replayed the same way research_trace is.
    doc_trace = Column(Text, nullable=True)

    # JSON-serialized artifact ({type, kind, language, title, content,
    # filename}) — a self-contained deliverable rendered in the canvas rather
    # than inline in the chat bubble.
    artifact = Column(Text, nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow)