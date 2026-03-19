from .database import init_db, get_connection

from .users import (
    get_user_by_telegram_id,
    create_user,
    get_or_create_user,
)

from .ads import (
    ad_exists,
    ad_seen_globally,
    count_global_ad_views,
    save_ad,
    update_ad_status,
    update_ad_draft,
    get_last_ad,
    get_ad_by_id,
    get_ad_by_ad_id,
)

from .pending_actions import (
    create_pending_action,
    update_pending_action_status,
    get_pending_actions,
    get_next_pending_action,
)

from .messages import (
    create_message,
)

from .templates import (
    ensure_default_template,
    get_active_template,
    update_active_template,
)

from .accounts import (
    create_account,
    get_account_by_id,
    get_user_accounts,
    update_account_status,
    update_account_profile_name,
    update_account_cookies,
    update_account_last_check,
    mark_account_checked,
    delete_account,
)

from .proxies import (
    create_proxy,
    create_proxies_bulk,
    get_proxy_by_id,
    get_user_proxies,
    get_next_available_proxy,
    update_proxy_status,
    update_proxy_last_check,
    mark_proxy_checked,
    delete_proxy,
)