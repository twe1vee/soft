import sqlite3

DB_FILE = "olx_assistant.db"


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT NOT NULL UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            price TEXT,
            seller_name TEXT,
            ad_id TEXT NOT NULL,
            status TEXT NOT NULL,
            draft_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, ad_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ad_id) REFERENCES ads(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ad_id) REFERENCES ads(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            template_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ads_user_id ON ads(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ads_user_status ON ads(user_id, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ads_ad_id ON ads(ad_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_status ON pending_actions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_ad_id ON pending_actions(ad_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_ad_id ON messages(ad_id)")

    conn.commit()
    conn.close()