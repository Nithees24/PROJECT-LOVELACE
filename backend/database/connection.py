from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from pathlib import Path
import os

# Anchor .env to the repo root — a CWD-relative search fails when the server
# is launched from another directory (BUG-14)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

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

        # Composite index so the recent-history query (ORDER BY timestamp
        # DESC LIMIT n per conversation) is fully index-served
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_messages_conversation_timestamp "
            "ON messages (conversation_id, timestamp)"
        ))
        conn.commit()

        # Deep-research trace column (plan + streamed activity events) so a
        # research run can be replayed when its conversation is reopened.
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'messages' AND column_name = 'research_trace'"
        ))
        if result.fetchone() is None:
            conn.execute(text("ALTER TABLE messages ADD COLUMN research_trace TEXT"))
            conn.commit()
            print("Migration: added 'research_trace' column to messages table.")

        # Document-agent trace (JSON): the brief, the interview Q&A and the
        # streamed activity, so a document run replays like a research one.
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'messages' AND column_name = 'doc_trace'"
        ))
        if result.fetchone() is None:
            conn.execute(text("ALTER TABLE messages ADD COLUMN doc_trace TEXT"))
            conn.commit()
            print("Migration: added 'doc_trace' column to messages table.")

        # Artifact column (JSON) — a self-contained deliverable (runnable HTML
        # page or code file) the assistant produced with this message, so it
        # can be reopened in the canvas when the conversation is reloaded.
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'messages' AND column_name = 'artifact'"
        ))
        if result.fetchone() is None:
            conn.execute(text("ALTER TABLE messages ADD COLUMN artifact TEXT"))
            conn.commit()
            print("Migration: added 'artifact' column to messages table.")

        # Session token column for bearer auth (SEC-01)
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'session_token'"
        ))
        if result.fetchone() is None:
            conn.execute(text("ALTER TABLE users ADD COLUMN session_token VARCHAR"))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_users_session_token "
                "ON users (session_token)"
            ))
            conn.commit()
            print("Migration: added 'session_token' column to users table.")

        # Session token expiry column (SEC-02)
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'session_expires_at'"
        ))
        if result.fetchone() is None:
            conn.execute(text("ALTER TABLE users ADD COLUMN session_expires_at TIMESTAMP"))
            conn.commit()
            print("Migration: added 'session_expires_at' column to users table.")

        # Verification-token issue timestamp (SEC-13): tokens must expire
        # after the 24h window the email advertises. Existing pending tokens
        # are backfilled with now() — one final 24h window instead of the
        # indefinite validity they had before.
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'verification_token_created_at'"
        ))
        if result.fetchone() is None:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN verification_token_created_at TIMESTAMP"
            ))
            backfilled = conn.execute(text(
                "UPDATE users SET verification_token_created_at = NOW() "
                "WHERE verification_token IS NOT NULL"
            ))
            conn.commit()
            print(
                "Migration: added 'verification_token_created_at' to users "
                f"(backfilled {backfilled.rowcount} pending tokens)."
            )

        # FK on messages.conversation_id — declared in the model but found
        # missing in the live DB (discovered during BUG-07 verification).
        result = conn.execute(text(
            "SELECT 1 FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            " AND tc.table_name = kcu.table_name "
            "WHERE tc.table_name = 'messages' "
            "  AND tc.constraint_type = 'FOREIGN KEY' "
            "  AND kcu.column_name = 'conversation_id'"
        ))
        if result.fetchone() is None:
            orphans = conn.execute(text(
                "DELETE FROM messages WHERE conversation_id NOT IN "
                "(SELECT id FROM conversations)"
            ))
            conn.execute(text(
                "ALTER TABLE messages ADD CONSTRAINT fk_messages_conversation_id "
                "FOREIGN KEY (conversation_id) REFERENCES conversations(id) "
                "ON DELETE CASCADE"
            ))
            conn.commit()
            print(
                "Migration: added FK messages.conversation_id -> conversations.id "
                f"(cleaned {orphans.rowcount} orphan messages)."
            )

        # FK on conversations.user_id (BUG-25). Existing orphan rows must be
        # removed first or the ALTER TABLE fails.
        # Detect ANY foreign key on conversations.user_id (a fresh create_all
        # names it differently than this migration does)
        result = conn.execute(text(
            "SELECT 1 FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            " AND tc.table_name = kcu.table_name "
            "WHERE tc.table_name = 'conversations' "
            "  AND tc.constraint_type = 'FOREIGN KEY' "
            "  AND kcu.column_name = 'user_id'"
        ))
        if result.fetchone() is None:
            orphan_msgs = conn.execute(text(
                "DELETE FROM messages WHERE conversation_id IN ("
                " SELECT c.id FROM conversations c LEFT JOIN users u ON c.user_id = u.id"
                " WHERE u.id IS NULL)"
            ))
            orphan_convs = conn.execute(text(
                "DELETE FROM conversations WHERE user_id NOT IN (SELECT id FROM users)"
            ))
            conn.execute(text(
                "ALTER TABLE conversations ADD CONSTRAINT fk_conversations_user_id "
                "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
            ))
            conn.commit()
            print(
                "Migration: added FK conversations.user_id -> users.id "
                f"(cleaned {orphan_convs.rowcount} orphan conversations, "
                f"{orphan_msgs.rowcount} of their messages)."
            )


def create_tables():
    Base.metadata.create_all(bind=engine)
    _run_migrations()