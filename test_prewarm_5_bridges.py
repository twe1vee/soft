from db import get_user_proxies
from olx.privoxy_pool import prewarm_privoxy_instances

USER_ID = 1  # подставь нужного пользователя

proxies = get_user_proxies(USER_ID)
proxy_texts = [p.get("proxy_text", "") for p in proxies]

results = prewarm_privoxy_instances(proxy_texts, limit=5)

print("=== PREWARM RESULTS ===")
for i, item in enumerate(results, start=1):
    print(f"{i}. {item}")