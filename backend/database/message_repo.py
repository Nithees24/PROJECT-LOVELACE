from sqlalchemy.orm import Session
from backend.database.message_model import Message


def save_message(db: Session, conversation_id: int, role: str, content: str, sources: str = None):
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        sources=sources
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message


def get_messages(db: Session, conversation_id: int):
    return (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.timestamp.asc())
        .all()
    )


def get_recent_messages(db: Session, conversation_id: int, limit: int = 20):
    """Bounded variant for the chat-context path: the DB does the limiting,
    not Python. Returns the last `limit` messages in chronological order."""
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.timestamp.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


def get_conversation_history(db: Session, conversation_id: int, limit: int = 20):
    """LLM-ready view of the recent history: [{"role", "content"}, ...].
    Single shared implementation for both entry points (BUG-23)."""
    return [
        {"role": msg.role, "content": msg.content}
        for msg in get_recent_messages(db, conversation_id, limit=limit)
    ]