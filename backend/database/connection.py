from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def _run_migrations():
    """Apply incremental schema migrations that create_all won't handle."""
    with engine.connect() as conn:
        # Add 'sources' column to messages table if it doesn't exist
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'messages' AND column_name = 'sources'"
        ))
        if result.fetchone() is None:
            conn.execute(text("ALTER TABLE messages ADD COLUMN sources TEXT"))
            conn.commit()
            print("Migration: added 'sources' column to messages table.")


def create_tables():
    Base.metadata.create_all(bind=engine)
    _run_migrations()