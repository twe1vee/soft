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
            INSERT INTO templates (user_id, template_text, image_path)
            VALUES (?, ?, NULL)
        """, (user_id, DEFAULT_TEMPLATE))

    conn.commit()
    conn.close()


def get_active_template(user_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, user_id, template_text, image_path, created_at, updated_at
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
            SET template_text = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (new_template_text, user_id))
    else:
        cursor.execute("""
            INSERT INTO templates (user_id, template_text, image_path)
            VALUES (?, ?, NULL)
        """, (user_id, new_template_text))

    conn.commit()
    conn.close()


def update_active_template_image(user_id: int, image_path: str):
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
            SET image_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (image_path, user_id))
    else:
        cursor.execute("""
            INSERT INTO templates (user_id, template_text, image_path)
            VALUES (?, ?, ?)
        """, (user_id, DEFAULT_TEMPLATE, image_path))

    conn.commit()
    conn.close()


def clear_active_template_image(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE templates
        SET image_path = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
    """, (user_id,))

    conn.commit()
    conn.close()