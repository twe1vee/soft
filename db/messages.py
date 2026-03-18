from db.database import get_connection


def create_message(ad_db_id: int, direction: str, text: str, status: str | None = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO messages (ad_id, direction, text, status)
        VALUES (?, ?, ?, ?)
    """, (ad_db_id, direction, text, status))

    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return message_id