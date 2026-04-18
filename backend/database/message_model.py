from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from datetime import datetime

from backend.database.connection import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), index=True)

    role = Column(String, nullable=False)  # "user" or "assistant"

    content = Column(Text, nullable=False)

    timestamp = Column(DateTime, default=datetime.utcnow)