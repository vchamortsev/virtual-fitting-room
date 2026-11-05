"""Коммерческое предложение. Цифры для страницы заказчика правятся здесь."""

SUBSCRIPTION_TIERS = (
    {"id": "start", "name": "Старт", "tryons": 300, "price_rub": 9900},
    {"id": "shop", "name": "Магазин", "tryons": 1000, "price_rub": 24000},
    {"id": "chain", "name": "Сеть", "tryons": 3000, "price_rub": 54000},
)
EXTRA_TRYON_RUB = 40
COMMISSION_PERCENT = 8
COMMISSION_WINDOW_HOURS = 24

PLAN_IDS = tuple(tier["id"] for tier in SUBSCRIPTION_TIERS) + ("commission", "undecided")


def public_offer() -> dict:
    return {
        "subscription": {
            "title": "Подписка на примерки",
            "summary": "Фиксированный пакет на месяц. Подходит, если примерки идут постоянно и их объём понятен заранее.",
            "extra_tryon_rub": EXTRA_TRYON_RUB,
            "tiers": [
                {**tier, "per_tryon_rub": round(tier["price_rub"] / tier["tryons"])}
                for tier in SUBSCRIPTION_TIERS
            ],
        },
        "commission": {
            "title": "Процент с покупки",
            "summary": "Абонентской платы нет. Оплата только если примерка привела к оплаченному заказу.",
            "percent": COMMISSION_PERCENT,
            "window_hours": COMMISSION_WINDOW_HOURS,
            "monthly_rub": 0,
        },
    }
