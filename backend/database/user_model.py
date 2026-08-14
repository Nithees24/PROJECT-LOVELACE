from sqlalchemy import Column, Integer, String, DateTime, Boolean
from datetime import datetime
from backend.database.connection import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    role = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    dob = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    verification_token = Column(String, nullable=True)
    verification_token_created_at = Column(DateTime, nullable=True)  # expiry anchor (SEC-13)
    session_token = Column(String, nullable=True, index=True)  # opaque bearer token issued at login (SEC-01)
    session_expires_at = Column(DateTime, nullable=True)  # token expiry (SEC-02)
    created_at = Column(DateTime, default=datetime.utcnow)
    resend_count = Column(Integer, default=0)
    last_resend_time = Column(DateTime, nullable=True)
