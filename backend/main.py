from backend.llm.llm_client import LLMClient
from backend.agents.general_chat_agent import GeneralChatAgent
from backend.agents.deep_research_agent import DeepResearchAgent
from backend.pipeline.planner import Planner
from backend.database.connection import SessionLocal
from backend.database.message_repo import save_message, get_messages

def get_conversation_history(db, conversation_id):
    messages = get_messages(db, conversation_id)
    history = [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]
    return history[-20:]

def main():
    llm_client = LLMClient()

    planner = Planner(llm_client)
    general_agent = GeneralChatAgent(llm_client)
    deep_agent = DeepResearchAgent(llm_client)

    db = SessionLocal()
    conversation_id = 999  # Dedicated conversation ID for CLI mode

    try:
        while True:
            user_query = input("\nUser:")
            
            save_message(db, conversation_id, "user", user_query)

            plan = planner.plan(user_query)

            print("\n[Planner Output]:", plan)

            mode = plan.get("mode")

            if mode == "normal":
                chat_history = get_conversation_history(db, conversation_id)
                response = general_agent.run_with_history(user_query, chat_history)
                save_message(db, conversation_id, "assistant", response)

            elif mode == "deep_research":
                response = deep_agent.run(user_query)
                save_message(db, conversation_id, "assistant", response)

            else:
                response = "Planner failed"

            print("\nAI:", response)
    finally:
        db.close()

if __name__ == "__main__":
    main()