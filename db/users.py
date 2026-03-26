from db.database import get_connection

def _row_to_dict(row):
    return dict(row) if row else None

def get_active_users() -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE is_active = 1
        ORDER BY id ASC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_user_by_telegram_id(telegram_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE telegram_id = ?",
        (str(telegram_id),)
    )
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)

def create_user(telegram_id: int, username: str | None, first_name: str | None, last_name: str | None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (telegram_id, username, first_name, last_name)
        VALUES (?, ?, ?, ?)
    """, (str(telegram_id), username, first_name, last_name))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id

def get_or_create_user(telegram_id: int, username: str | None, first_name: str | None, last_name: str | None) -> dict:
    user = get_user_by_telegram_id(telegram_id)
    if user:
        return user

    user_id = create_user(telegram_id, username, first_name, last_name)
    return {
        "id": user_id,
        "telegram_id": str(telegram_id),
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
    }