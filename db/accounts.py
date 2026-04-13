import time

from db.database import get_connection


def _row_to_dict(row):
    return dict(row) if row else None


def _normalize_market(market: str | None) -> str:
    value = (market or "olx_pt").strip().lower()
    return value or "olx_pt"


def touch_account_last_used(account_id: int, ts: int | None = None) -> bool:
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
    threshold = int(time.time()) - int(idle_seconds)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, user_id, olx_profile_name, gologin_profile_id, gologin_profile_name, last_used_at, market
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
    threshold = int(time.time()) - int(idle_seconds)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            a.id,
            a.user_id,
            a.olx_profile_name,
            a.gologin_profile_id,
            a.gologin_profile_name,
            a.market,
            u.last_active_at AS user_last_active_at
        FROM accounts a
        INNER JOIN users u ON u.id = a.user_id
        WHERE a.gologin_profile_id IS NOT NULL
          AND TRIM(a.gologin_profile_id) != ''
          AND u.last_active_at IS NOT NULL
          AND u.last_active_at < ?
        ORDER BY a.id ASC
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
    market: str = "olx_pt",
) -> int:
    now_ts = int(time.time())
    normalized_market = _normalize_market(market)

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
            market
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
            normalized_market,
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
    normalized_status = (new_status or "").strip().lower()
    now_ts = int(time.time())

    conn = get_connection()
    cursor = conn.cursor()

    if normalized_status == "write_blocked":
        cursor.execute(
            """
            UPDATE accounts
            SET status = ?,
                write_blocked_at = COALESCE(write_blocked_at, ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (normalized_status, now_ts, account_id, user_id),
        )
    else:
        cursor.execute(
            """
            UPDATE accounts
            SET status = ?,
                write_blocked_at = CASE
                    WHEN ? != 'write_blocked' THEN NULL
                    ELSE write_blocked_at
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (normalized_status, normalized_status, account_id, user_id),
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


def update_account_market(user_id: int, account_id: int, market: str):
    normalized_market = _normalize_market(market)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET market = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (normalized_market, account_id, user_id),
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
        SELECT id
        FROM conversations
        WHERE user_id = ? AND account_id = ?
        """,
        (user_id, account_id),
    )
    conversation_rows = cursor.fetchall()
    conversation_ids = [int(row["id"]) for row in conversation_rows]

    if conversation_ids:
        placeholders = ",".join("?" for _ in conversation_ids)
        cursor.execute(
            f"""
            DELETE FROM conversation_messages
            WHERE conversation_id IN ({placeholders})
            """,
            tuple(conversation_ids),
        )

    cursor.execute(
        """
        DELETE FROM conversations
        WHERE user_id = ? AND account_id = ?
        """,
        (user_id, account_id),
    )

    cursor.execute(
        """
        DELETE FROM accounts
        WHERE id = ? AND user_id = ?
        """,
        (account_id, user_id),
    )

    conn.commit()
    conn.close()


def ensure_accounts_write_blocked_column():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(accounts)")
    columns = {str(row["name"]) for row in cursor.fetchall()}
    if "write_blocked_at" not in columns:
        cursor.execute(
            "ALTER TABLE accounts ADD COLUMN write_blocked_at INTEGER DEFAULT NULL"
        )
        conn.commit()
    conn.close()


def mark_account_write_blocked(user_id: int, account_id: int, ts: int | None = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET status = 'write_blocked',
            write_blocked_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (int(ts or time.time()), int(account_id), int(user_id)),
    )
    conn.commit()
    conn.close()


def clear_account_write_blocked(user_id: int, account_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE accounts
        SET write_blocked_at = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (int(account_id), int(user_id)),
    )
    conn.commit()
    conn.close()


def get_expired_write_blocked_accounts_with_profiles(grace_seconds: int) -> list[dict]:
    threshold = int(time.time()) - int(grace_seconds)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            user_id,
            status,
            olx_profile_name,
            gologin_profile_id,
            gologin_profile_name,
            write_blocked_at,
            last_used_at,
            market
        FROM accounts
        WHERE status = 'write_blocked'
          AND write_blocked_at IS NOT NULL
          AND write_blocked_at < ?
        ORDER BY id ASC
        """,
        (threshold,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]