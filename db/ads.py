from db.database import get_connection


def ad_exists(user_id: int, ad_id: str | None) -> bool:
    if not ad_id:
        return False

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM ads
        WHERE user_id = ? AND ad_id = ?
    """, (user_id, ad_id))
    row = cursor.fetchone()

    conn.close()
    return row is not None


def save_ad(user_id: int, ad_data: dict) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO ads (
            user_id,
            url,
            price,
            seller_name,
            ad_id,
            status,
            draft_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        ad_data.get("url"),
        ad_data.get("price"),
        ad_data.get("seller_name"),
        ad_data.get("ad_id"),
        ad_data.get("status"),
        ad_data.get("draft_text"),
    ))

    ad_row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ad_row_id


def get_ad_by_id(user_id: int, ad_db_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM ads
        WHERE id = ? AND user_id = ?
        LIMIT 1
    """, (ad_db_id, user_id))
    row = cursor.fetchone()

    conn.close()
    return dict(row) if row else None


def get_ad_by_ad_id(user_id: int, ad_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM ads
        WHERE user_id = ? AND ad_id = ?
        LIMIT 1
    """, (user_id, ad_id))
    row = cursor.fetchone()

    conn.close()
    return dict(row) if row else None


def get_last_ad(user_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM ads
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (user_id,))
    row = cursor.fetchone()

    conn.close()
    return dict(row) if row else None


def update_ad_status(user_id: int, ad_db_id: int, new_status: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE ads
        SET status = ?
        WHERE id = ? AND user_id = ?
    """, (new_status, ad_db_id, user_id))

    conn.commit()
    conn.close()


def update_ad_draft(
    user_id: int,
    ad_db_id: int,
    new_draft_text: str,
    new_status: str | None = None,
):
    conn = get_connection()
    cursor = conn.cursor()

    if new_status is not None:
        cursor.execute("""
            UPDATE ads
            SET draft_text = ?, status = ?
            WHERE id = ? AND user_id = ?
        """, (new_draft_text, new_status, ad_db_id, user_id))
    else:
        cursor.execute("""
            UPDATE ads
            SET draft_text = ?
            WHERE id = ? AND user_id = ?
        """, (new_draft_text, ad_db_id, user_id))

    conn.commit()
    conn.close()