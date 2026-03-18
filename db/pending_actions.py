from db.database import get_connection


def create_pending_action(ad_db_id: int, action_type: str, payload_text: str | None = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO pending_actions (ad_id, action_type, status, payload_text)
        VALUES (?, ?, ?, ?)
    """, (ad_db_id, action_type, "pending", payload_text))

    action_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return action_id


def update_pending_action_status(action_id: int, new_status: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE pending_actions SET status = ? WHERE id = ?",
        (new_status, action_id),
    )

    conn.commit()
    conn.close()


def get_pending_actions(status: str = "pending") -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            pa.id AS action_id,
            pa.ad_id AS ad_id,
            pa.action_type AS action_type,
            pa.status AS status,
            pa.payload_text AS payload_text,
            a.seller_name AS seller_name,
            a.price AS price
        FROM pending_actions pa
        LEFT JOIN ads a ON a.id = pa.ad_id
        WHERE pa.status = ?
        ORDER BY pa.id DESC
    """, (status,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_next_pending_action() -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            pa.id AS action_id,
            pa.ad_id AS ad_id,
            pa.action_type AS action_type,
            pa.status AS action_status,
            pa.payload_text AS payload_text,
            a.seller_name AS seller_name,
            a.price AS price
        FROM pending_actions pa
        LEFT JOIN ads a ON a.id = pa.ad_id
        WHERE pa.status = 'pending'
        ORDER BY pa.id ASC
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None