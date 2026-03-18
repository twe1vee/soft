from db.database import get_connection


def _row_to_dict(row):
    return dict(row) if row else None


def ad_exists(ad_id: str | None) -> bool:
    if not ad_id:
        return False

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM ads WHERE ad_id = ?", (ad_id,))
    row = cursor.fetchone()

    conn.close()
    return row is not None


def save_ad(ad_data: dict) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO ads (url, price, seller_name, ad_id, status, draft_text)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
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


def get_ad_by_id(ad_db_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ads WHERE id = ?", (ad_db_id,))
    row = cursor.fetchone()

    conn.close()
    return _row_to_dict(row)


def get_ad_by_ad_id(ad_id: str) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ads WHERE ad_id = ?", (ad_id,))
    row = cursor.fetchone()

    conn.close()
    return _row_to_dict(row)


def get_last_ad() -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM ads ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()

    conn.close()
    return _row_to_dict(row)


def update_ad_status(ad_db_id: int, new_status: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE ads SET status = ? WHERE id = ?",
        (new_status, ad_db_id),
    )

    conn.commit()
    conn.close()


def update_ad_draft(ad_db_id: int, new_draft_text: str, new_status: str | None = None):
    conn = get_connection()
    cursor = conn.cursor()

    if new_status:
        cursor.execute(
            "UPDATE ads SET draft_text = ?, status = ? WHERE id = ?",
            (new_draft_text, new_status, ad_db_id),
        )
    else:
        cursor.execute(
            "UPDATE ads SET draft_text = ? WHERE id = ?",
            (new_draft_text, ad_db_id),
        )

    conn.commit()
    conn.close()