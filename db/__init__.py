from .database import init_db, get_connection, DB_FILE

from .users import (
    get_user_by_telegram_id,
    create_user,
    get_or_create_user,
    get_active_users,
    touch_user_last_active,
    update_user_profile_fields,
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
    update_account_proxy,
    update_account_last_check,
    mark_account_checked,
    delete_account,
    update_account_gologin_profile,
    update_account_browser_engine,
    clear_account_gologin_profile,
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

from .conversations import (
    create_or_update_conversation,
    get_conversation_by_id,
    get_conversation_by_key,
    get_user_conversations,
    update_conversation_read_state,
    update_conversation_last_preview,
)

from .conversation_messages import (
    conversation_message_exists,
    create_conversation_message,
    get_last_conversation_message,
    get_conversation_messages,
    get_new_conversation_messages_for_user,
    mark_conversation_message_notified,
)

__all__ = [
    "init_db",
    "get_connection",
    "DB_FILE",
    "get_user_by_telegram_id",
    "create_user",
    "get_or_create_user",
    "get_active_users",
    "touch_user_last_active",
    "update_user_profile_fields",
    "ad_exists",
    "ad_seen_globally",
    "count_global_ad_views",
    "save_ad",
    "update_ad_status",
    "update_ad_draft",
    "get_last_ad",
    "get_ad_by_id",
    "get_ad_by_ad_id",
    "create_pending_action",
    "update_pending_action_status",
    "get_pending_actions",
    "get_next_pending_action",
    "create_message",
    "ensure_default_template",
    "get_active_template",
    "update_active_template",
    "create_account",
    "get_account_by_id",
    "get_user_accounts",
    "update_account_status",
    "update_account_profile_name",
    "update_account_cookies",
    "update_account_proxy",
    "update_account_last_check",
    "mark_account_checked",
    "delete_account",
    "update_account_gologin_profile",
    "update_account_browser_engine",
    "clear_account_gologin_profile",
    "create_proxy",
    "create_proxies_bulk",
    "get_proxy_by_id",
    "get_user_proxies",
    "get_next_available_proxy",
    "update_proxy_status",
    "update_proxy_last_check",
    "mark_proxy_checked",
    "delete_proxy",
    "create_or_update_conversation",
    "get_conversation_by_id",
    "get_conversation_by_key",
    "get_user_conversations",
    "update_conversation_read_state",
    "update_conversation_last_preview",
    "conversation_message_exists",
    "create_conversation_message",
    "get_last_conversation_message",
    "get_conversation_messages",
    "get_new_conversation_messages_for_user",
    "mark_conversation_message_notified",
]