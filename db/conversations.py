from __future__ import annotations

from db.database import get_connection


def _row_to_dict(row):
    return dict(row) if row else None


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
    return _row_to_dict(row)


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
    return _row_to_dict(row)


def get_user_conversations(
    user_id: int,
    *,
    account_id: int | None = None,
    status: str | None = None,
    unread_only: bool = False,
    limit: int = 100,
) -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()

    query = """
        SELECT *
        FROM conversations
        WHERE user_id = ?
    """
    params: list = [user_id]

    if account_id is not None:
        query += " AND account_id = ?"
        params.append(account_id)

    if status is not None:
        query += " AND status = ?"
        params.append(status)

    if unread_only:
        query += " AND is_unread = 1"

    query += """
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
    """
    params.append(limit)

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_or_update_conversation(
    *,
    user_id: int,
    account_id: int,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                account_id,
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


def update_conversation_read_state(
    user_id: int,
    conversation_id: int,
    *,
    is_unread: bool,
) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE conversations
        SET
            is_unread = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND user_id = ?
        """,
        (1 if is_unread else 0, conversation_id, user_id),
    )
    conn.commit()
    conn.close()


def update_conversation_last_preview(
    user_id: int,
    conversation_id: int,
    *,
    last_message_preview: str | None,
    last_message_at_hint: str | None = None,
    last_incoming_message_key: str | None = None,
) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE conversations
        SET
            last_message_preview = ?,
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