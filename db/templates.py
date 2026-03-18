from db.database import get_connection

DEFAULT_TEMPLATE = (
    "Здравствуйте! Товар еще актуален?\n"
    "Подскажите, пожалуйста, в каком он состоянии?"
)


def ensure_default_template(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM templates
        WHERE user_id = ?
        LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute("""
            INSERT INTO templates (user_id, template_text)
            VALUES (?, ?)
        """, (user_id, DEFAULT_TEMPLATE))

    conn.commit()
    conn.close()


def get_active_template(user_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, user_id, template_text, created_at
        FROM templates
        WHERE user_id = ?
        LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()

    conn.close()
    return dict(row) if row else None


def update_active_template(user_id: int, new_template_text: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM templates
        WHERE user_id = ?
        LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()

    if row:
        cursor.execute("""
            UPDATE templates
            SET template_text = ?
            WHERE user_id = ?
        """, (new_template_text, user_id))
    else:
        cursor.execute("""
            INSERT INTO templates (user_id, template_text)
            VALUES (?, ?)
        """, (user_id, new_template_text))

    conn.commit()
    conn.close()