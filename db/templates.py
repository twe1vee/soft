from db.database import get_connection

DEFAULT_TEMPLATE = (
    "Здравствуйте! Объявление еще актуально?\n"
    "Интересует цена {price}. "
    "Я увидел объявление по ссылке: {url}"
)


def _row_to_dict(row):
    return dict(row) if row else None


def ensure_default_template():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM templates WHERE is_active = 1 LIMIT 1")
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            "INSERT INTO templates (template_text, is_active) VALUES (?, 1)",
            (DEFAULT_TEMPLATE,),
        )
        conn.commit()

    conn.close()


def get_active_template() -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM templates
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()

    conn.close()
    return _row_to_dict(row)


def update_active_template(new_template_text: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE templates
        SET template_text = ?
        WHERE id = (
            SELECT id FROM templates
            WHERE is_active = 1
            ORDER BY id DESC
            LIMIT 1
        )
    """, (new_template_text,))

    conn.commit()
    conn.close()