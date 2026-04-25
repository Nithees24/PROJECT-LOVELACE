from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from datetime import datetime
from backend.database.connection import Base

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    title = Column(String, nullable=False, default="New Conversation")
    created_at = Column(DateTime, default=datetime.utcnow)
    is_pinned = Column(Boolean, default=False, nullable=False)
    pinned_at = Column(DateTime, nullable=True)
    rating = Column(Integer, default=0, nullable=False)
