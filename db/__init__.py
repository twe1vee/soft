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
    get_ad_by_id,
    get_ad_by_ad_id,
    get_last_ad,
    update_ad_status,
    update_ad_draft,
)

from .templates import (
    ensure_default_template,
    get_active_template,
    update_active_template,
)

from .pending_actions import (
    create_pending_action,
    update_pending_action_status,
    get_pending_actions,
    get_next_pending_action,
)

from .messages import create_message