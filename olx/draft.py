from db import get_active_template
from olx.template_service import render_template

DEFAULT_TEMPLATE = (
    "Здравствуйте, {seller_name}!\n\n"
    "Меня заинтересовало ваше объявление на OLX.\n"
    "Цена в объявлении: {price}.\n"
    "Подскажите, пожалуйста, актуально ли оно?\n"
    "Если да, хотел бы уточнить несколько деталей.\n\n"
    "Ссылка: {url}"
)


def generate_draft(user_id: int, ad_data: dict) -> str:
    template = get_active_template(user_id)
    template_text = template["template_text"] if template else DEFAULT_TEMPLATE
    return render_template(template_text, ad_data)