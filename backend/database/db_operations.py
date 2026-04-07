def get_conversation_history(db, conversation_id):
    query = """
    SELECT role, content
    FROM messages
    WHERE conversation_id = %s
    ORDER BY timestamp DESC
    LIMIT 20
    """

    cursor = db.cursor()
    cursor.execute(query, (conversation_id,))
    rows = cursor.fetchall()

    # convert to list of dicts (important!)
    history = [
        {"role": row[0], "content": row[1]}
        for row in rows
    ]

    # reverse to chronological order
    return list(reversed(history))