from backend.utils.logger import logger
from backend.llm.llm_client import LLMClient
from backend.agents.general_chat_agent import GeneralChatAgent
from backend.agents.deep_research_agent import DeepResearchAgent
from backend.pipeline.planner import Planner
from backend.database.connection import SessionLocal, create_tables
from backend.database.conversation_model import Conversation
from backend.database.user_model import User
from backend.database.message_repo import save_message, get_conversation_history

CLI_USER_EMAIL = "cli@localhost"  # system user row backing local CLI sessions
CLI_CONVERSATION_TITLE = "CLI Session"


def get_or_create_cli_user(db):
    """Real user row for CLI sessions so conversations satisfy the FK to
    users.id (BUG-25). The password hash is intentionally not a valid
    SHA-256 digest and the account is unverified, so it can never log in
    through the web API."""
    user = db.query(User).filter(User.email == CLI_USER_EMAIL).first()
    if user is None:
        user = User(
            email=CLI_USER_EMAIL,
            password_hash="!cli-local-session-no-login",
            first_name="CLI",
            last_name="Session",
            is_verified=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created CLI system user with id {user.id}")
    return user.id


def get_or_create_cli_conversation(db):
    """Reuse (or create) a real conversation row for CLI mode so that saved
    messages satisfy the FK to conversations.id (BUG-06)."""
    cli_user_id = get_or_create_cli_user(db)
    conv = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == cli_user_id,
            Conversation.title == CLI_CONVERSATION_TITLE,
        )
        .order_by(Conversation.created_at.desc())
        .first()
    )
    if conv is None:
        conv = Conversation(user_id=cli_user_id, title=CLI_CONVERSATION_TITLE)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        logger.info(f"Created CLI conversation with id {conv.id}")
    return conv.id

def main():
    logger.info("Starting CLI mode session.")
    llm_client = LLMClient()
    llm_client.probe()  # fail loudly at boot on a bad model name (BUG-02)

    planner = Planner(llm_client)
    general_agent = GeneralChatAgent(llm_client)
    deep_agent = DeepResearchAgent(llm_client)

    create_tables()
    db = SessionLocal()
    conversation_id = get_or_create_cli_conversation(db)

    try:
        while True:
            try:
                user_query = input("\nUser:")
            except (KeyboardInterrupt, EOFError):
                print()
                logger.info("CLI mode session ended by user interrupt.")
                break
                
            logger.info(f"User query received in CLI: {user_query}")
            save_message(db, conversation_id, "user", user_query)

            plan = planner.plan(user_query)

            print("\n[Planner Output]:", plan)
            logger.info(f"Planner output generated: {plan}")

            mode = plan.get("mode")

            if mode == "normal":
                chat_history = get_conversation_history(db, conversation_id)
                response, sources = general_agent.run_with_history(user_query, chat_history)
                save_message(db, conversation_id, "assistant", response)

            elif mode == "deep_research":
                response, sources = deep_agent.run(user_query)
                save_message(db, conversation_id, "assistant", response)

            else:
                response = "Planner failed"
                logger.error(f"Invalid mode from planner: {mode}")

            print("\nAI:", response)
            logger.info(f"AI response provided: {response}")
    except Exception as e:
        logger.error(f"Unhandled error in CLI loop: {e}", exc_info=True)
    finally:
        db.close()
        logger.info("CLI mode session closed.")

if __name__ == "__main__":
    main()