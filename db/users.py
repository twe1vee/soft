from db.database import get_connection
import time


def _row_to_dict(row):
    return dict(row) if row else None


def get_active_users() -> list[dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE is_active = 1
        ORDER BY id ASC
        """
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (int(user_id),))
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)


def get_user_by_telegram_id(telegram_id: int) -> dict | None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM users WHERE telegram_id = ?",
        (str(telegram_id),)
    )
    row = cursor.fetchone()
    conn.close()
    return _row_to_dict(row)


def create_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> int:
    now_ts = int(time.time())

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO users (telegram_id, username, first_name, last_name, last_active_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(telegram_id), username, first_name, last_name, now_ts),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


def touch_user_last_active(user_id: int, ts: int | None = None) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users
        SET last_active_at = ?
        WHERE id = ?
        """,
        (int(ts or time.time()), int(user_id)),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def update_user_profile_fields(
    user_id: int,
    *,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users
        SET username = ?, first_name = ?, last_name = ?
        WHERE id = ?
        """,
        (username, first_name, last_name, int(user_id)),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def get_or_create_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> dict:
    user = get_user_by_telegram_id(telegram_id)
    if user:
        update_user_profile_fields(
            user["id"],
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        touch_user_last_active(user["id"])
        user["username"] = username
        user["first_name"] = first_name
        user["last_name"] = last_name
        user["last_active_at"] = int(time.time())
        return user

    user_id = create_user(telegram_id, username, first_name, last_name)
    return {
        "id": user_id,
        "telegram_id": str(telegram_id),
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "last_active_at": int(time.time()),
    }


def update_user_redscript_token(user_id: int, access_token: str | None) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users
        SET redscript_access_token = ?
        WHERE id = ?
        """,
        ((access_token or "").strip() or None, int(user_id)),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def clear_user_redscript_token(user_id: int) -> bool:
    return update_user_redscript_token(user_id, None)


def update_user_redscript_defaults(
    user_id: int,
    *,
    initials: str | None = None,
    address: str | None = None,
    mail_service: str | None = None,
    country: str | None = None,
    type_value: str | None = None,
    service: str | None = None,
    version: str | None = None,
) -> bool:
    updates: list[str] = []
    values: list[object] = []

    if initials is not None:
        updates.append("redscript_initials = ?")
        values.append((initials or "").strip() or None)

    if address is not None:
        updates.append("redscript_address = ?")
        values.append((address or "").strip() or None)

    if mail_service is not None:
        updates.append("redscript_mail_service = ?")
        values.append((mail_service or "").strip() or None)

    if country is not None:
        updates.append("redscript_country = ?")
        values.append((country or "").strip() or None)

    if type_value is not None:
        updates.append("redscript_type = ?")
        values.append((type_value or "").strip() or None)

    if service is not None:
        updates.append("redscript_service = ?")
        values.append((service or "").strip() or None)

    if version is not None:
        updates.append("redscript_version = ?")
        values.append((version or "").strip() or None)

    if not updates:
        return False

    values.append(int(user_id))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        UPDATE users
        SET {", ".join(updates)}
        WHERE id = ?
        """,
        tuple(values),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed