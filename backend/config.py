import os

PRODUCTION = os.getenv("PRODUCTION", "False").lower() == "true"

LLM_MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.2