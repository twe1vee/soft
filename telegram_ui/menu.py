from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Обработать ссылки 🔗", callback_data="menu:process_links"),
        ],
        [
            InlineKeyboardButton("📨 Отправить письмо", callback_data="menu:redscript"),
        ],
        [
            InlineKeyboardButton("Аккаунт 👤", callback_data="menu:account"),
            InlineKeyboardButton("Прокси 🌐", callback_data="menu:proxies"),
            InlineKeyboardButton("Шаблоны 📝", callback_data="menu:templates"),
        ],
        [
            InlineKeyboardButton("Настройка софта ⚙️", callback_data="menu:settings"),
        ],
    ])


def get_templates_menu_keyboard(has_image: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("👁 Текущий шаблон", callback_data="templates:preview"),
        ],
        [
            InlineKeyboardButton("✏️ Изменить текст", callback_data="templates:edit_text"),
        ],
        [
            InlineKeyboardButton("🖼 Загрузить фото", callback_data="templates:upload_image"),
        ],
    ]

    if has_image:
        rows.append([
            InlineKeyboardButton("❌ Удалить фото", callback_data="templates:remove_image"),
        ])

    rows.append([
        InlineKeyboardButton("⬅️ Вернуться в главное меню", callback_data="menu:main"),
    ])

    return InlineKeyboardMarkup(rows)


def get_template_preview_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад к шаблону", callback_data="templates:back")]
    ])


def build_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Вернуться в главное меню", callback_data="menu:main")]
    ])


def build_action_keyboard(ad_row_id: int, action_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data=f"approve:{ad_row_id}:{action_id}"),
            InlineKeyboardButton("Edit", callback_data=f"edit:{ad_row_id}:{action_id}"),
            InlineKeyboardButton("Reject", callback_data=f"reject:{ad_row_id}:{action_id}"),
        ]
    ])