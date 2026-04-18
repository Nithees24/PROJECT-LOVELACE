import os

PRODUCTION = os.getenv("PRODUCTION", "False").lower() == "true"

# Fast model for general chat — low latency
CHAT_MODEL = "gemini-3.1-flash-lite-preview"

# Powerful model for deep research — higher quality
LLM_MODEL = "gemma-4-31b-it"

TEMPERATURE = 0.2