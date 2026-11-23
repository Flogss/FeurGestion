"""IA de FeurBot via l'API Groq (compatible OpenAI). La clé vient de la variable GROQ_API_KEY."""

import asyncio
import logging
import os
import ssl

import aiohttp
import certifi

log = logging.getLogger(__name__)

API = "https://api.groq.com/openai/v1/chat/completions"
MODELS = [os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), "qwen/qwen3.8-27b"]  # le 2e sert de secours

SYSTEM = (
    "Tu es FeurBot, le bot du groupe Telegram « feurchat ». Tu parles français, avec humour et second degré, "
    "comme un pote un peu chambreur, jamais méchant. Tu adores la blague « quoi ? feur » et tu la places "
    "de temps en temps, sans en abuser. Réponds court : 1 à 5 phrases, sauf si on te demande explicitement "
    "quelque chose de long. Pas de tableaux, pas de titres. Si tu ne sais pas, dis-le. Refuse poliment "
    "(et avec une vanne) les demandes haineuses, illégales ou dangereuses. Tu ne peux ni bannir ni muter : "
    "c'est le travail des admins. La personne qui te parle s'appelle {name}."
)

_session: aiohttp.ClientSession | None = None
_slots = asyncio.Semaphore(3)


class AIError(Exception):
    pass


def enabled() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))


async def ask(messages: list[dict], name: str) -> str:
    """`messages` : l'historique [{"role": "user"|"assistant", "content": ...}]. Retourne la réponse."""
    return await complete([{"role": "system", "content": SYSTEM.format(name=name)}, *messages], 700)


async def complete(payload_messages: list[dict], max_tokens: int) -> str:
    global _session
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise AIError("pas de clé")
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=90),
            connector=aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where())),
        )
    async with _slots:
        last_error = None
        for model in MODELS:
            try:
                async with _session.post(
                    API,
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "messages": payload_messages, "max_tokens": max_tokens, "temperature": 0.8},
                ) as response:
                    data = await response.json(content_type=None)
                if response.status == 200 and data.get("choices"):
                    content = (data["choices"][0]["message"].get("content") or "").strip()
                    if content:
                        return content
                last_error = (data.get("error") or {}).get("message", f"HTTP {response.status}")
            except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                last_error = str(exc)
            log.warning("IA %s indisponible : %s", model, last_error)
        raise AIError(last_error or "pas de réponse")


async def close() -> None:
    if _session and not _session.closed:
        await _session.close()
