from db.database import get_connection


def _row_to_dict(row):
    return dict(row) if row else None


def create_proxy(
    user_id: int,
    proxy_text: str,
    status: str = "new",
) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO proxies (
            user_id,
            proxy_text,
            status
        )
        VALUES (?, ?, ?)
    """, (user_id, proxy_text, status))

    proxy_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return proxy_id


def create_proxies_bulk(user_id: int, proxy_list: list[str]) -> int:
    cleaned = []
    seen = set()

    for proxy_text in proxy_list:
        value = proxy_text.strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        cleaned.append((user_id, value, "new"))

    if not cleaned:
        return 0

    conn = get_connection()
    cursor = conn.cursor()

    cursor.executemany("""
        INSERT INTO proxies (
            user_id,
            proxy_text,
            status
        )
        VALUES (?, ?, ?)
    """, cleaned)

    inserted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return inserted_count


def get_proxy_by_id(user_id: int, proxy_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM proxies
        WHERE id = ? AND user_id = ?
        LIMIT 1
    """, (proxy_id, user_id))

    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)


def get_user_proxies(user_id: int) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM proxies
        WHERE user_id = ?
        ORDER BY id ASC
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_next_available_proxy(user_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM proxies
        WHERE user_id = ?
          AND status IN ('new', 'working')
        ORDER BY id ASC
        LIMIT 1
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)


def update_proxy_status(user_id: int, proxy_id: int, new_status: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE proxies
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (new_status, proxy_id, user_id))

    conn.commit()
    conn.close()


def update_proxy_last_check(user_id: int, proxy_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE proxies
        SET last_check_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (proxy_id, user_id))

    conn.commit()
    conn.close()


def mark_proxy_checked(user_id: int, proxy_id: int, status: str = "working"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE proxies
        SET status = ?,
            last_check_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
    """, (status, proxy_id, user_id))

    conn.commit()
    conn.close()


def delete_proxy(user_id: int, proxy_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM proxies
        WHERE id = ? AND user_id = ?
    """, (proxy_id, user_id))

    conn.commit()
    conn.close()