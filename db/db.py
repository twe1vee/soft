import sqlite3
from typing import Optional

DB_FILE = "olx_assistant.db"


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            price TEXT,
            seller_name TEXT,
            ad_id TEXT UNIQUE,
            status TEXT NOT NULL,
            draft_text TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_text TEXT,
            FOREIGN KEY (ad_id) REFERENCES ads(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ad_id) REFERENCES ads(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            template_text TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ads_ad_id ON ads(ad_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ads_status ON ads(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_ad_id ON pending_actions(ad_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_status ON pending_actions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_ad_id ON messages(ad_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_templates_active ON templates(is_active)")

    conn.commit()
    conn.close()

    ensure_default_template()


def ensure_default_template():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM templates LIMIT 1")
    row = cursor.fetchone()

    if not row:
        cursor.execute("""
            INSERT INTO templates (name, template_text, is_active)
            VALUES (?, ?, 1)
        """, (
            "Основной шаблон",
            "Здравствуйте, {seller_name}!\n\n"
            "Меня заинтересовало ваше объявление на OLX.\n"
            "Цена в объявлении: {price}.\n"
            "Подскажите, пожалуйста, актуально ли оно?\n"
            "Если да, хотел бы уточнить несколько деталей.\n\n"
            "Ссылка: {url}"
        ))
        conn.commit()

    conn.close()


def get_active_template():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM templates
        WHERE is_active = 1
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_active_template(new_text: str):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE templates
        SET template_text = ?, updated_at = CURRENT_TIMESTAMP
        WHERE is_active = 1
    """, (new_text,))
    conn.commit()
    conn.close()


def ad_exists(ad_id: Optional[str]) -> bool:
    if not ad_id:
        return False

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM ads WHERE ad_id = ?", (ad_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def get_ad_by_ad_id(ad_id: str):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ads WHERE ad_id = ?", (ad_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_ad_by_id(ad_db_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ads WHERE id = ?", (ad_db_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_last_ad():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM ads
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_ads_by_status(status: str) -> list[dict]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM ads
        WHERE status = ?
        ORDER BY id DESC
    """, (status,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_ad(ad_data: dict) -> int:
    conn = get_conn()
    cursor = conn.cursor()

    ad_id = ad_data.get("ad_id")

    if ad_id:
        cursor.execute("SELECT id FROM ads WHERE ad_id = ?", (ad_id,))
        existing = cursor.fetchone()
        if existing:
            conn.close()
            return existing["id"]

    cursor.execute("""
        INSERT INTO ads (url, price, seller_name, ad_id, status, draft_text)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        ad_data["url"],
        ad_data.get("price"),
        ad_data.get("seller_name"),
        ad_id,
        ad_data.get("status", "new"),
        ad_data.get("draft_text"),
    ))

    ad_row_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return ad_row_id


def update_ad_status(ad_db_id: int, new_status: str):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE ads
        SET status = ?
        WHERE id = ?
    """, (new_status, ad_db_id))
    conn.commit()
    conn.close()


def update_ad_draft(ad_db_id: int, draft_text: str, new_status: str = "draft_ready"):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE ads
        SET draft_text = ?, status = ?
        WHERE id = ?
    """, (draft_text, new_status, ad_db_id))
    conn.commit()
    conn.close()


def create_pending_action(
    ad_db_id: int,
    action_type: str,
    payload_text: Optional[str] = None,
    status: str = "pending",
) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pending_actions (ad_id, action_type, status, payload_text)
        VALUES (?, ?, ?, ?)
    """, (ad_db_id, action_type, status, payload_text))
    action_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return action_id


def update_pending_action_status(action_id: int, new_status: str):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE pending_actions
        SET status = ?
        WHERE id = ?
    """, (new_status, action_id))
    conn.commit()
    conn.close()


def get_pending_actions(status: str = "pending") -> list[dict]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            pa.id AS action_id,
            pa.ad_id,
            pa.action_type,
            pa.status AS action_status,
            pa.payload_text,
            a.url,
            a.price,
            a.seller_name,
            a.ad_id AS external_ad_id,
            a.status AS ad_status,
            a.draft_text
        FROM pending_actions pa
        JOIN ads a ON a.id = pa.ad_id
        WHERE pa.status = ?
        ORDER BY pa.id ASC
    """, (status,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_next_pending_action():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            pa.id AS action_id,
            pa.ad_id,
            pa.action_type,
            pa.status AS action_status,
            pa.payload_text,
            a.url,
            a.price,
            a.seller_name,
            a.ad_id AS external_ad_id,
            a.status AS ad_status,
            a.draft_text
        FROM pending_actions pa
        JOIN ads a ON a.id = pa.ad_id
        WHERE pa.status = 'pending'
        ORDER BY pa.id ASC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_action_by_id(action_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            pa.id AS action_id,
            pa.ad_id,
            pa.action_type,
            pa.status AS action_status,
            pa.payload_text,
            a.url,
            a.price,
            a.seller_name,
            a.ad_id AS external_ad_id,
            a.status AS ad_status,
            a.draft_text
        FROM pending_actions pa
        JOIN ads a ON a.id = pa.ad_id
        WHERE pa.id = ?
        LIMIT 1
    """, (action_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def create_message(ad_db_id: int, direction: str, text: str, status: str) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO messages (ad_id, direction, text, status)
        VALUES (?, ?, ?, ?)
    """, (ad_db_id, direction, text, status))
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return message_id


def get_messages_for_ad(ad_db_id: int) -> list[dict]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM messages
        WHERE ad_id = ?
        ORDER BY id ASC
    """, (ad_db_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_last_outgoing_message(ad_db_id: int):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM messages
        WHERE ad_id = ? AND direction = 'outgoing'
        ORDER BY id DESC
        LIMIT 1
    """, (ad_db_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None