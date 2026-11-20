import random
from html import escape

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, User

from ..config import Config
from ..content import MEDIA_LABELS, extract_media, html_args, render, send_content
from ..db import Database
from ..filters import IsAdmin
from ..utils import PREFIXES, shorten

router = Router(name="welcome")

# Une variante est tirée au hasard à chaque arrivée (jamais deux fois la même d'affilée)
DEFAULT_TEXTS = [
    "👋 Bienvenue {mention} sur <b>{chat}</b> ! Règle n°1 : ici on ne dit pas « quoi ». Tu sais très bien pourquoi. 😏",
    "🚪 Toc toc ? C'est {mention} ! Entre, essuie tes pieds, et surtout ne dis jamais « quoi ».",
    "🎉 Un membre sauvage apparaît : {mention} ! Il utilise « Dire bonjour ». C'est super efficace. (Membre n°{count})",
    "🛬 {mention} vient d'atterrir sur <b>{chat}</b>. Bagages : aucun. Blagues nulles : bientôt mille.",
    "📢 Attention tout le monde, {mention} est là ! Faites semblant d'être normaux.",
    "🍕 {mention} a rejoint le groupe. Les pizzas sont pour les admins, désolé. Les blagues, elles, sont gratuites.",
    "🧪 Expérience n°{count} : on ajoute {mention} au groupe et on observe. Bonne chance.",
    "👀 {mention} est arrivé. Petit conseil de survie : si on te dit « quoi », réponds « feur ».",
    "🎬 Et voici {mention}, dans le rôle du petit nouveau. Membre n°{count}. Action !",
    "🫡 Bienvenue soldat {mention}. Ta mission : survivre aux blagues. Tes chances : faibles.",
    "🔔 Ding dong, {mention} est entré. Les admins t'ont à l'œil. Enfin, quand ils sont réveillés.",
    "🌶 {mention} débarque sur <b>{chat}</b> ! Tape <code>/flocko</code> pour connaître ton taux de flocko. C'est vital.",
]
# Ancien message unique : remplacé par les variantes s'il n'avait pas été personnalisé
OLD_DEFAULT = (
    "👋 Bienvenue {mention} sur <b>{chat}</b> !\n"
    "Règle n°1 : ici on ne dit pas « quoi ». Tu sais très bien pourquoi. 😏"
)
DEFAULT_WELCOME = {"enabled": True, "texts": DEFAULT_TEXTS, "media_type": None, "media_id": None}

_last_pick: dict[str, str | None] = {"text": None}


async def get_welcome(db: Database) -> dict:
    stored = await db.get_setting("welcome", {})
    conf = {**DEFAULT_WELCOME, **stored}
    if "texts" not in stored:
        old = stored.get("text")
        conf["texts"] = list(DEFAULT_TEXTS) + ([old] if old and old != OLD_DEFAULT else [])
    conf.pop("text", None)
    conf["texts"] = list(conf["texts"])
    return conf


def pick_text(texts: list[str]) -> str:
    choices = [text for text in texts if text != _last_pick["text"]] or texts
    _last_pick["text"] = random.choice(choices)
    return _last_pick["text"]


async def greet(user: User, bot: Bot, db: Database, cfg: Config) -> None:
    conf = await get_welcome(db)
    if conf["enabled"]:
        text = await render(pick_text(conf["texts"]), user, bot, cfg)
        await send_content(bot, cfg.chat_id, text, conf["media_type"], conf["media_id"])


async def _preview(message: Message, conf: dict, text: str, bot: Bot, cfg: Config) -> None:
    rendered = await render(text, message.from_user, bot, cfg)
    await send_content(bot, message.chat.id, rendered, conf["media_type"], conf["media_id"])


async def _save_with_preview(message: Message, conf: dict, text: str, bot: Bot, db: Database, cfg: Config) -> bool:
    try:
        await _preview(message, conf, text, bot, cfg)
    except TelegramBadRequest as exc:
        await message.reply(f"❌ Telegram n'en veut pas : {escape(exc.message)}")
        return False
    await db.set_setting("welcome", conf)
    return True


@router.message(Command("welcome", "bienvenue", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_welcome(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    conf = await get_welcome(db)
    args = (command.args or "").strip()
    keyword = args.split()[0].lower() if args else ""

    if keyword in ("on", "off") and len(args.split()) == 1:
        conf["enabled"] = keyword == "on"
        await db.set_setting("welcome", conf)
        await message.reply(
            "✅ Bienvenue activée. Les nouveaux seront accueillis comme des rois (ou presque)."
            if conf["enabled"]
            else "⛔️ Bienvenue désactivée. Les nouveaux entreront dans un silence gênant."
        )
        return

    if keyword in ("reset", "nomedia") and len(args.split()) == 1:
        if keyword == "reset":
            conf = {**DEFAULT_WELCOME, "texts": list(DEFAULT_TEXTS)}
        else:
            conf["media_type"] = conf["media_id"] = None
        await db.set_setting("welcome", conf)
        await _preview(message, conf, pick_text(conf["texts"]), bot, cfg)
        await message.reply(f"✅ C'est fait. {len(conf['texts'])} variante(s), en voici une ☝️")
        return

    if keyword in ("list", "liste") and len(args.split()) == 1:
        lines = [f"<b>👋 {len(conf['texts'])} variante(s) de bienvenue</b> (une au hasard à chaque arrivée)"]
        lines += [f"<b>{index}.</b> {escape(shorten(text, 160))}" for index, text in enumerate(conf["texts"], 1)]
        lines.append("\n<code>.welcome add texte</code> · <code>.welcome del 3</code>")
        await message.reply("\n".join(lines))
        return

    if keyword in ("del", "suppr"):
        number = args.split()[1] if len(args.split()) > 1 else ""
        if not number.isdigit() or not 1 <= int(number) <= len(conf["texts"]):
            await message.reply(f"Usage : <code>.welcome del 3</code> (numéro entre 1 et {len(conf['texts'])}, voir <code>.welcome list</code>).")
            return
        if len(conf["texts"]) == 1:
            await message.reply("❌ C'est la dernière variante. Sans elle, je bégaie. Change-la plutôt.")
            return
        conf["texts"].pop(int(number) - 1)
        await db.set_setting("welcome", conf)
        await message.reply(f"🗑 Variante {number} supprimée. Il en reste {len(conf['texts'])}.")
        return

    media_type, media_id = extract_media(message)
    if not media_type:
        media_type, media_id = extract_media(message.reply_to_message)
    if media_type:
        conf["media_type"], conf["media_id"] = media_type, media_id

    if keyword == "add":
        text = html_args(message, 2)
        if not text:
            await message.reply("Usage : <code>.welcome add Salut {mention} !</code>")
            return
        conf["texts"].append(text)
        if await _save_with_preview(message, conf, text, bot, db, cfg):
            await message.reply(f"✅ Variante ajoutée ({len(conf['texts'])} au total). Aperçu ☝️")
        return

    new_text = html_args(message)
    if not new_text and not media_type:
        state = "✅ activée" if conf["enabled"] else "⛔️ désactivée"
        await message.reply(
            f"<b>👋 Message de bienvenue</b> — {state}\n"
            f"Variantes : {len(conf['texts'])} (une au hasard à chaque arrivée)\n"
            f"Média : {MEDIA_LABELS.get(conf['media_type'], 'aucun')}\n"
            "Aperçu avec toi dans le rôle du petit nouveau ⬇️"
        )
        await _preview(message, conf, pick_text(conf["texts"]), bot, cfg)
        return

    if new_text:
        conf["texts"] = [new_text]
    if await _save_with_preview(message, conf, conf["texts"][0] if new_text else pick_text(conf["texts"]), bot, db, cfg):
        note = "" if not new_text else "\n<i>C'est maintenant l'unique variante. <code>.welcome add</code> pour en ajouter d'autres.</i>"
        await message.reply(f"✅ Enregistré ! Aperçu ☝️ (oui, c'est toi le nouveau pour l'occasion){note}")
