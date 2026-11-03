import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


def _parse_chat_id(raw: str) -> int:
    value = int(raw.strip())
    # Les clients Telegram affichent souvent l'ID d'un supergroupe sans le préfixe -100
    if value > 0:
        value = int(f"-100{value}")
    return value


def _parse_ids(raw: str) -> frozenset[int]:
    return frozenset(int(part) for part in raw.replace(" ", "").split(",") if part)


@dataclass(frozen=True)
class Config:
    token: str
    chat_id: int
    admin_ids: frozenset[int]
    log_chat_id: int | None
    db_path: str
    tz: ZoneInfo


def load_config() -> Config:
    admin_ids = _parse_ids(os.environ["ADMIN_IDS"])
    if not admin_ids:
        raise RuntimeError("ADMIN_IDS doit contenir au moins un ID")

    # Par défaut les logs partent en privé au premier admin ; "off" pour les couper
    raw_log = os.getenv("LOG_CHAT_ID", "").strip()
    if raw_log.lower() in ("off", "0", "none"):
        log_chat_id = None
    elif raw_log:
        log_chat_id = int(raw_log)
    else:
        log_chat_id = min(admin_ids)

    return Config(
        token=os.environ["BOT_TOKEN"].strip(),
        chat_id=_parse_chat_id(os.environ["CHAT_ID"]),
        admin_ids=admin_ids,
        log_chat_id=log_chat_id,
        db_path=os.getenv("DB_PATH", "data/feurgestion.db"),
        tz=ZoneInfo(os.getenv("TZ", "Europe/Paris")),
    )
