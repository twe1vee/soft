from db.database import get_connection


def _row_to_dict(row):
    return dict(row) if row else None


def create_account(
    user_id: int,
    cookies_json: str,
    status: str = "new",
    olx_profile_name: str | None = None,
) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO accounts (
            user_id,
            olx_profile_name,
            cookies_json,
            status
        )
        VALUES (?, ?, ?, ?)
    """, (user_id, olx_profile_name, cookies_json, status))

    account_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return account_id


def get_account_by_id(user_id: int, account_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM accounts
        WHERE id = ? AND user_id = ?
        LIMIT 1
    """, (account_id, user_id))

    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)


def get_user_accounts(user_id: int) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM accounts
        WHERE user_id = ?
        ORDER BY id ASC
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_account_status(user_id: int, account_id: int, new_status: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE accounts
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (new_status, account_id, user_id))

    conn.commit()
    conn.close()


def update_account_profile_name(
    user_id: int,
    account_id: int,
    olx_profile_name: str | None,
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE accounts
        SET olx_profile_name = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (olx_profile_name, account_id, user_id))

    conn.commit()
    conn.close()


def update_account_cookies(user_id: int, account_id: int, cookies_json: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE accounts
        SET cookies_json = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (cookies_json, account_id, user_id))

    conn.commit()
    conn.close()


def update_account_proxy(user_id: int, account_id: int, proxy_id: int | None):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE accounts
        SET proxy_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (proxy_id, account_id, user_id))

    conn.commit()
    conn.close()


def update_account_last_check(user_id: int, account_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE accounts
        SET last_check_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (account_id, user_id))

    conn.commit()
    conn.close()


def mark_account_checked(user_id: int, account_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE accounts
        SET status = 'checked',
            last_check_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (account_id, user_id))

    conn.commit()
    conn.close()


def delete_account(user_id: int, account_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM accounts
        WHERE id = ? AND user_id = ?
    """, (account_id, user_id))

    conn.commit()
    conn.close()