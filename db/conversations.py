from db.database import get_connection


def create_or_update_conversation(
    *,
    user_id: int,
    account_id: int,
    ad_id: int | None = None,
    conversation_key: str,
    conversation_url: str | None = None,
    seller_name: str | None = None,
    ad_title: str | None = None,
    ad_url: str | None = None,
    ad_external_id: str | None = None,
    last_message_preview: str | None = None,
    last_message_at_hint: str | None = None,
    is_unread: bool = False,
    last_incoming_message_key: str | None = None,
    status: str = "active",
) -> int:
    existing = get_conversation_by_key(user_id, account_id, conversation_key)

    conn = get_connection()
    cursor = conn.cursor()

    if existing:
        cursor.execute(
            """
            UPDATE conversations
            SET
                ad_id = COALESCE(?, ad_id),
                conversation_url = COALESCE(?, conversation_url),
                seller_name = COALESCE(?, seller_name),
                ad_title = COALESCE(?, ad_title),
                ad_url = COALESCE(?, ad_url),
                ad_external_id = COALESCE(?, ad_external_id),
                last_message_preview = COALESCE(?, last_message_preview),
                last_message_at_hint = COALESCE(?, last_message_at_hint),
                is_unread = ?,
                last_incoming_message_key = COALESCE(?, last_incoming_message_key),
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                ad_id,
                conversation_url,
                seller_name,
                ad_title,
                ad_url,
                ad_external_id,
                last_message_preview,
                last_message_at_hint,
                1 if is_unread else 0,
                last_incoming_message_key,
                status,
                existing["id"],
            ),
        )
        conversation_id = existing["id"]
    else:
        cursor.execute(
            """
            INSERT INTO conversations (
                user_id,
                account_id,
                ad_id,
                conversation_key,
                conversation_url,
                seller_name,
                ad_title,
                ad_url,
                ad_external_id,
                last_message_preview,
                last_message_at_hint,
                is_unread,
                last_incoming_message_key,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                account_id,
                ad_id,
                conversation_key,
                conversation_url,
                seller_name,
                ad_title,
                ad_url,
                ad_external_id,
                last_message_preview,
                last_message_at_hint,
                1 if is_unread else 0,
                last_incoming_message_key,
                status,
            ),
        )
        conversation_id = cursor.lastrowid

    conn.commit()
    conn.close()
    return conversation_id


def get_conversation_by_key(
    user_id: int,
    account_id: int,
    conversation_key: str,
) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM conversations
        WHERE user_id = ? AND account_id = ? AND conversation_key = ?
        LIMIT 1
        """,
        (user_id, account_id, conversation_key),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_conversation_by_id(
    user_id: int,
    conversation_id: int,
) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM conversations
        WHERE id = ? AND user_id = ?
        LIMIT 1
        """,
        (conversation_id, user_id),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_conversations_for_account(
    user_id: int,
    account_id: int,
    *,
    only_unread: bool = False,
    limit: int = 50,
) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    if only_unread:
        cursor.execute(
            """
            SELECT *
            FROM conversations
            WHERE user_id = ? AND account_id = ? AND is_unread = 1
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, account_id, limit),
        )
    else:
        cursor.execute(
            """
            SELECT *
            FROM conversations
            WHERE user_id = ? AND account_id = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, account_id, limit),
        )

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_conversation_read(
    user_id: int,
    conversation_id: int,
) -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE conversations
        SET
            is_unread = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (conversation_id, user_id),
    )

    conn.commit()
    conn.close()


def update_conversation_last_preview(
    user_id: int,
    conversation_id: int,
    *,
    last_message_preview: str | None = None,
    last_message_at_hint: str | None = None,
    last_incoming_message_key: str | None = None,
) -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE conversations
        SET
            last_message_preview = COALESCE(?, last_message_preview),
            last_message_at_hint = COALESCE(?, last_message_at_hint),
            last_incoming_message_key = COALESCE(?, last_incoming_message_key),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (
            last_message_preview,
            last_message_at_hint,
            last_incoming_message_key,
            conversation_id,
            user_id,
        ),
    )

    conn.commit()
    conn.close()