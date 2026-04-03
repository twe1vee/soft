import sqlite3

DB_FILE = "olx_assistant.db"


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table_name})")
    rows = cursor.fetchall()
    return any(row["name"] == column_name for row in rows)


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT NOT NULL UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active_at INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            price TEXT,
            location TEXT,
            seller_name TEXT,
            seller_url TEXT,
            ad_id TEXT NOT NULL,
            status TEXT NOT NULL,
            draft_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, ad_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payload_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ad_id) REFERENCES ads(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            text TEXT NOT NULL,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ad_id) REFERENCES ads(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            template_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            proxy_text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',
            last_check_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            olx_profile_name TEXT,
            cookies_json TEXT NOT NULL,
            proxy_id INTEGER,
            status TEXT NOT NULL DEFAULT 'new',
            browser_engine TEXT NOT NULL DEFAULT 'gologin',
            gologin_profile_id TEXT,
            gologin_profile_name TEXT,
            last_check_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (proxy_id) REFERENCES proxies(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            ad_id INTEGER,
            conversation_key TEXT NOT NULL,
            conversation_url TEXT,
            seller_name TEXT,
            ad_title TEXT,
            ad_url TEXT,
            ad_external_id TEXT,
            last_message_preview TEXT,
            last_message_at_hint TEXT,
            is_unread INTEGER NOT NULL DEFAULT 0,
            last_incoming_message_key TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id),
            FOREIGN KEY (ad_id) REFERENCES ads(id),
            UNIQUE(account_id, conversation_key)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            external_message_key TEXT NOT NULL,
            direction TEXT NOT NULL,
            sender_name TEXT,
            text TEXT NOT NULL,
            is_unread INTEGER NOT NULL DEFAULT 0,
            sent_at_hint TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            notified_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id),
            FOREIGN KEY (account_id) REFERENCES accounts(id),
            UNIQUE(conversation_id, external_message_key)
        )
        """
    )

    if not _column_exists(cursor, "users", "last_active_at"):
        cursor.execute("ALTER TABLE users ADD COLUMN last_active_at INTEGER")

    if not _column_exists(cursor, "accounts", "proxy_id"):
        cursor.execute("ALTER TABLE accounts ADD COLUMN proxy_id INTEGER")

    if not _column_exists(cursor, "accounts", "created_at"):
        cursor.execute("ALTER TABLE accounts ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    if not _column_exists(cursor, "accounts", "updated_at"):
        cursor.execute("ALTER TABLE accounts ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    if not _column_exists(cursor, "accounts", "browser_engine"):
        cursor.execute("ALTER TABLE accounts ADD COLUMN browser_engine TEXT NOT NULL DEFAULT 'gologin'")

    if not _column_exists(cursor, "accounts", "gologin_profile_id"):
        cursor.execute("ALTER TABLE accounts ADD COLUMN gologin_profile_id TEXT")

    if not _column_exists(cursor, "accounts", "gologin_profile_name"):
        cursor.execute("ALTER TABLE accounts ADD COLUMN gologin_profile_name TEXT")

    if not _column_exists(cursor, "proxies", "created_at"):
        cursor.execute("ALTER TABLE proxies ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    if not _column_exists(cursor, "proxies", "updated_at"):
        cursor.execute("ALTER TABLE proxies ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    if not _column_exists(cursor, "conversations", "ad_external_id"):
        cursor.execute("ALTER TABLE conversations ADD COLUMN ad_external_id TEXT")

    if not _column_exists(cursor, "conversations", "last_message_at_hint"):
        cursor.execute("ALTER TABLE conversations ADD COLUMN last_message_at_hint TEXT")

    if not _column_exists(cursor, "conversations", "last_incoming_message_key"):
        cursor.execute("ALTER TABLE conversations ADD COLUMN last_incoming_message_key TEXT")

    if not _column_exists(cursor, "conversation_messages", "notified_at"):
        cursor.execute("ALTER TABLE conversation_messages ADD COLUMN notified_at TIMESTAMP")

    if not _column_exists(cursor, "conversation_messages", "updated_at"):
        cursor.execute("ALTER TABLE conversation_messages ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_last_active_at ON users(last_active_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ads_user_id ON ads(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ads_user_status ON ads(user_id, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ads_ad_id ON ads(ad_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_status ON pending_actions(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_ad_id ON pending_actions(ad_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_ad_id ON messages(ad_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user_status ON accounts(user_id, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_proxy_id ON accounts(proxy_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_gologin_profile_id ON accounts(gologin_profile_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_browser_engine ON accounts(browser_engine)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_proxies_user_id ON proxies(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_proxies_user_status ON proxies(user_id, status)")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_account_id ON conversations(account_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_user_status ON conversations(user_id, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_account_unread ON conversations(account_id, is_unread)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_key ON conversations(account_id, conversation_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_id ON conversation_messages(conversation_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_messages_account_id ON conversation_messages(account_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_messages_notify ON conversation_messages(notified_at)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_key ON "
        "conversation_messages(conversation_id, external_message_key)"
    )

    conn.commit()
    conn.close()