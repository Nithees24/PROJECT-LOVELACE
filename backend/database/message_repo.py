import json

from sqlalchemy.orm import Session
from backend.database.message_model import Message


def save_message(db: Session, conversation_id: int, role: str, content: str,
                 sources: str = None, research_trace: str = None,
                 artifact: str = None, doc_trace: str = None):
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        sources=sources,
        research_trace=research_trace,
        artifact=artifact,
        doc_trace=doc_trace,
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
    Single shared implementation for both entry points (BUG-23).

    Artifact source is re-attached to the MOST RECENT artifact message. The
    stored `content` has the artifact block stripped out (it lives in its own
    column), so without this the model cannot see what it previously built and
    a follow-up like "make the button blue" forces a rebuild from scratch.

    Only the latest artifact carries its full source — earlier ones are
    reduced to a one-line mention. Replaying every artifact would blow up the
    prompt (they run 8-13k chars each) for code the user has moved on from.
    """
    messages = get_recent_messages(db, conversation_id, limit=limit)

    # Index of the last message that carries an artifact.
    latest_idx = -1
    for i, msg in enumerate(messages):
        if getattr(msg, "artifact", None):
            latest_idx = i

    history = []
    for i, msg in enumerate(messages):
        content = msg.content
        raw = getattr(msg, "artifact", None)
        if raw:
            try:
                art = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                art = None
            if art:
                title = art.get("title", "artifact")
                if i == latest_idx:
                    lang = art.get("language") or art.get("type") or ""
                    content = (
                        f"{content}\n\n"
                        f"[The artifact you produced — \"{title}\". This is the "
                        f"current version; when the user asks for changes, edit "
                        f"THIS code and return the complete updated artifact.]\n"
                        f"```{lang}\n{art.get('content', '')}\n```"
                    )
                else:
                    content = f"{content}\n\n[You produced an earlier artifact: \"{title}\".]"
        history.append({"role": msg.role, "content": content})
    return history