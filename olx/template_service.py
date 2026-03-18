def render_template(template_text: str, ad_data: dict) -> str:
    seller_name = ad_data.get("seller_name") or ""
    price = ad_data.get("price") or ""
    url = ad_data.get("url") or ""

    return (
        template_text
        .replace("{seller_name}", seller_name)
        .replace("{price}", price)
        .replace("{url}", url)
    )