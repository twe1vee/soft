from db.database import get_connection


def _norm_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


def get_ad_by_user_account_seller_title(
    user_id: int,
    account_id: int,
    seller_name: str | None,
    ad_title: str | None,
) -> dict | None:
    """
    Боевой безопасный fallback для входящих диалогов.

    Вариант A:
    не зависим от pending_actions/send_jobs, потому что на части клиентских БД
    таблицы send_jobs ещё нет, а send queue сейчас живёт in-memory.

    Ищем среди объявлений пользователя по seller_name / title.
    account_id пока оставляем в сигнатуре только для совместимости вызовов.
    """
    seller_norm = _norm_text(seller_name)
    title_norm = _norm_text(ad_title)

    if not seller_norm and not title_norm:
        return None

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT *
        FROM ads
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    items = [dict(row) for row in rows]

    # 1. Самый сильный матч: seller + title
    for item in items:
        row_seller = _norm_text(item.get("seller_name"))
        row_title = _norm_text(item.get("title"))

        seller_ok = bool(seller_norm and row_seller and seller_norm == row_seller)
        title_ok = bool(title_norm and row_title and title_norm == row_title)

        if seller_ok and title_ok:
            return item

    # 2. Fallback: только title
    for item in items:
        row_title = _norm_text(item.get("title"))
        if title_norm and row_title and title_norm == row_title:
            return item

    # 3. Fallback: только seller
    for item in items:
        row_seller = _norm_text(item.get("seller_name"))
        if seller_norm and row_seller and seller_norm == row_seller:
            return item

    return None


def get_ad_by_user_ad_external_id(
    user_id: int,
    ad_external_id: str | None,
) -> dict | None:
    if not ad_external_id:
        return None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT *
        FROM ads
        WHERE user_id = ? AND ad_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (user_id, ad_external_id),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


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


def ad_seen_globally(ad_id: str | None) -> bool:
    if not ad_id:
        return False

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM ads
        WHERE ad_id = ?
        LIMIT 1
    """, (ad_id,))
    row = cursor.fetchone()

    conn.close()
    return row is not None


def count_global_ad_views(ad_id: str | None) -> int:
    if not ad_id:
        return 0

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM ads
        WHERE ad_id = ?
    """, (ad_id,))
    row = cursor.fetchone()

    conn.close()
    return row[0] if row else 0


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


def update_ad_external_id(
    user_id: int,
    ad_db_id: int,
    ad_external_id: str | None,
):
    value = (ad_external_id or "").strip()
    if not value:
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE ads
        SET ad_id = ?
        WHERE id = ? AND user_id = ?
    """, (value, ad_db_id, user_id))

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