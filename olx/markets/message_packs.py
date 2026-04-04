from __future__ import annotations


def get_message_pack(market_code: str = "olx_pt") -> dict:
    normalized = (market_code or "olx_pt").strip().lower()

    packs = {
        "olx_pt": {
            "delivery_verified_texts": [
                "entregue",
                "enviado",
                "mensagem enviada",
            ],
            "delivery_failed_texts": [
                "falhou",
                "não foi possível enviar",
                "nao foi possivel enviar",
                "erro ao enviar",
            ],
            "login_texts": [
                "iniciar sessão",
                "inicia sessão",
                "entrar",
                "login",
            ],
            "empty_dialog_texts": [
                "sem mensagens",
                "nenhuma mensagem",
                "ainda não tens mensagens",
                "não tem mensagens",
            ],
            "button_texts": {
                "close": ["fechar"],
                "accept": ["aceitar", "aceitar tudo"],
                "continue": ["continuar"],
                "ok": ["ok", "entendi"],
                "send": ["enviar"],
            },
        },
        "olx_pl": {
            "delivery_verified_texts": [
                "dostarczono",
                "wysłano",
                "wiadomość wysłana",
            ],
            "delivery_failed_texts": [
                "nie udało się wysłać",
                "blad wysylania",
                "błąd wysyłania",
                "niepowodzenie",
            ],
            "login_texts": [
                "zaloguj",
                "logowanie",
                "zaloguj się",
            ],
            "empty_dialog_texts": [
                "brak wiadomości",
                "nie masz jeszcze wiadomości",
            ],
            "button_texts": {
                "close": ["zamknij"],
                "accept": ["akceptuj"],
                "continue": ["kontynuuj"],
                "ok": ["ok"],
                "send": ["wyślij", "wyslij"],
            },
        },
    }

    return packs.get(normalized, packs["olx_pt"])