from __future__ import annotations

from db.database import get_connection


def _row_to_dict(row):
    return dict(row) if row else None


def conversation_message_exists(
    conversation_id: int,
    external_message_key: str,
) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1
        FROM conversation_messages
        WHERE conversation_id = ? AND external_message_key = ?
        LIMIT 1
        """,
        (conversation_id, external_message_key),
    )
    row = cursor.fetchone()
    conn.close()
    return row is not None


def create_conversation_message(
    *,
    conversation_id: int,
    account_id: int,
    external_message_key: str,
    direction: str,
    sender_name: str | None,
    text: str,
    is_unread: bool = False,
    sent_at_hint: str | None = None,
    status: str = "new",
    notified_at: str | None = None,
) -> int | None:
    if conversation_message_exists(conversation_id, external_message_key):
        return None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO conversation_messages (
            conversation_id,
            account_id,
            external_message_key,
            direction,
            sender_name,
            text,
            is_unread,
            sent_at_hint,
            status,
            notified_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            conversation_id,
            account_id,
            external_message_key,
            direction,
            sender_name,
            text,
            1 if is_unread else 0,
            sent_at_hint,
            status,
            notified_at,
        ),
    )
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return message_id


def get_last_conversation_message(
    conversation_id: int,
) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM conversation_messages
        WHERE conversation_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (conversation_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)


def get_conversation_messages(
    conversation_id: int,
    *,
    limit: int = 100,
) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM conversation_messages
        WHERE conversation_id = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (conversation_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_new_conversation_messages_for_user(
    user_id: int,
    *,
    limit: int = 100,
) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            cm.*,
            c.user_id,
            c.conversation_key,
            c.conversation_url,
            c.seller_name AS conversation_seller_name,
            c.ad_title,
            c.ad_url,
            c.last_message_preview
        FROM conversation_messages cm
        JOIN conversations c ON c.id = cm.conversation_id
        WHERE c.user_id = ?
          AND cm.direction = 'incoming'
          AND cm.notified_at IS NULL
        ORDER BY cm.id ASC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_conversation_message_notified(
    message_id: int,
) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE conversation_messages
        SET
            notified_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (message_id,),
    )
    conn.commit()
    conn.close()