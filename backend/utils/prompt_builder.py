def build_prompt_with_history(user_query, history):

    SYSTEM_PROMPT = """You are Lovelace, an advanced, highly capable, and engaging AI assistant.

    Your response style should dynamically adapt based on the user's input:
    
    1. IF the user is simply greeting you:
       - Respond with a short greeting.
    
    2. IF the user asks a substantive question:
       - Provide a structured, engaging, markdown-formatted answer.
       - Use bold titles (**Title 🌟**) instead of # headers.
       - Use subtitles, bullet points, emojis, and a "Related Topics" section.
    
    IMPORTANT:
    - Maintain conversational continuity using previous messages.
    - If the user refers to earlier context, use it naturally.
    - Do NOT repeat past answers unless necessary.
    """

    # 🔥 Build conversation history
    conversation = ""

    for msg in history:
        role = "User" if msg["role"] == "user" else "Lovelace"
        conversation += f"{role}: {msg['content']}\n"

    prompt = f"""{SYSTEM_PROMPT}

    Conversation History:
    {conversation}
    
    User Question:
    {user_query}
    
    Answer:
    """

    return prompt