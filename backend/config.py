import os

PRODUCTION = os.getenv("PRODUCTION", "False").lower() == "true"

# Fast model for general chat — low latency
CHAT_MODEL = "gemini-2.0-flash"

# Powerful model for deep research — higher quality
LLM_MODEL = "gemma-4-31b-it"

TEMPERATURE = 0.2