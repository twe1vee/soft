from db.database import get_connection
import time


def _row_to_dict(row):
    return dict(row) if row else None


def ensure_accounts_last_used_column():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(accounts)")
    columns = {str(row["name"]) for row in cursor.fetchall()}
    if "last_used_at" not in columns:
        cursor.execute(
            "ALTER TABLE accounts ADD COLUMN last_used_at INTEGER DEFAULT NULL"
        )
        conn.commit()
    conn.close()


def ensure_accounts_user_last_active_column():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(accounts)")
    columns = {str(row["name"]) for row in cursor.fetchall()}
    if "user_last_active_at" not in columns:
        cursor.execute(
            "ALTER TABLE accounts ADD COLUMN user_last_active_at INTEGER DEFAULT NULL"
        )
        conn.commit()
    conn.close()


def ensure_accounts_activity_columns():
    ensure_accounts_last_used_column()
    ensure_accounts_user_last_active_column()


def touch_account_last_used(account_id: int, ts: int | None = None) -> bool:
    ensure_accounts_last_used_column()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET last_used_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (int(ts or time.time()), int(account_id)),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def touch_account_user_active(account_id: int, ts: int | None = None) -> bool:
    ensure_accounts_user_last_active_column()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET user_last_active_at = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (int(ts or time.time()), int(account_id)),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def clear_account_gologin_binding_by_account_id(account_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET gologin_profile_id = NULL,
            gologin_profile_name = NULL,
            browser_engine = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (int(account_id),),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def get_stale_accounts_with_profiles(idle_seconds: int) -> list[dict]:
    ensure_accounts_last_used_column()
    threshold = int(time.time()) - int(idle_seconds)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, olx_profile_name, gologin_profile_id, gologin_profile_name, last_used_at
        FROM accounts
        WHERE gologin_profile_id IS NOT NULL
          AND TRIM(gologin_profile_id) != ''
          AND last_used_at IS NOT NULL
          AND last_used_at < ?
        ORDER BY id ASC
        """,
        (threshold,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_stale_user_inactive_accounts_with_profiles(idle_seconds: int) -> list[dict]:
    ensure_accounts_user_last_active_column()
    threshold = int(time.time()) - int(idle_seconds)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            user_id,
            olx_profile_name,
            gologin_profile_id,
            gologin_profile_name,
            user_last_active_at
        FROM accounts
        WHERE user_last_active_at IS NOT NULL
          AND user_last_active_at < ?
        ORDER BY id ASC
        """,
        (threshold,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_account(
    user_id: int,
    cookies_json: str,
    status: str = "new",
    olx_profile_name: str | None = None,
    browser_engine: str = "gologin",
) -> int:
    ensure_accounts_activity_columns()

    now_ts = int(time.time())

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO accounts (
            user_id,
            olx_profile_name,
            cookies_json,
            status,
            browser_engine,
            last_used_at,
            user_last_active_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            olx_profile_name,
            cookies_json,
            status,
            browser_engine,
            now_ts,
            now_ts,
        ),
    )
    account_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return account_id


def get_account_by_id(user_id: int, account_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM accounts
        WHERE id = ? AND user_id = ?
        LIMIT 1
        """,
        (account_id, user_id),
    )
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)


def get_user_accounts(user_id: int) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM accounts
        WHERE user_id = ?
        ORDER BY id ASC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_account_status(user_id: int, account_id: int, new_status: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (new_status, account_id, user_id),
    )
    conn.commit()
    conn.close()


def update_account_profile_name(
    user_id: int,
    account_id: int,
    olx_profile_name: str | None,
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET olx_profile_name = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (olx_profile_name, account_id, user_id),
    )
    conn.commit()
    conn.close()


def update_account_cookies(user_id: int, account_id: int, cookies_json: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET cookies_json = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (cookies_json, account_id, user_id),
    )
    conn.commit()
    conn.close()


def update_account_proxy(user_id: int, account_id: int, proxy_id: int | None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET proxy_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (proxy_id, account_id, user_id),
    )
    conn.commit()
    conn.close()


def update_account_last_check(user_id: int, account_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET last_check_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (account_id, user_id),
    )
    conn.commit()
    conn.close()


def mark_account_checked(user_id: int, account_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET status = 'checked', last_check_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (account_id, user_id),
    )
    conn.commit()
    conn.close()


def update_account_gologin_profile(
    user_id: int,
    account_id: int,
    gologin_profile_id: str | None,
    gologin_profile_name: str | None = None,
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET gologin_profile_id = ?, gologin_profile_name = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (gologin_profile_id, gologin_profile_name, account_id, user_id),
    )
    conn.commit()
    conn.close()


def update_account_browser_engine(
    user_id: int,
    account_id: int,
    browser_engine: str,
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET browser_engine = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (browser_engine, account_id, user_id),
    )
    conn.commit()
    conn.close()


def clear_account_gologin_profile(
    user_id: int,
    account_id: int,
):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET gologin_profile_id = NULL,
            gologin_profile_name = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (account_id, user_id),
    )
    conn.commit()
    conn.close()


def delete_account(user_id: int, account_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM accounts
        WHERE id = ? AND user_id = ?
        """,
        (account_id, user_id),
    )
    conn.commit()
    conn.close()