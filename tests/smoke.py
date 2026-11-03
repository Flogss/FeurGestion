"""Test de bout en bout sans réseau : on simule l'API Telegram et on envoie de faux messages au bot.

Lancer : python tests/smoke.py
"""

import asyncio
import os
import sys
import tempfile
import time
import traceback
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.update(BOT_TOKEN="9006812840:TEST", CHAT_ID="3940270802", ADMIN_IDS="8925708293")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.methods import (  # noqa: E402
    AnswerCallbackQuery,
    BanChatMember,
    DeleteMessages,
    EditMessageText,
    ForwardMessage,
    GetChat,
    GetChatMember,
    GetChatMemberCount,
    GetMe,
    RestrictChatMember,
    SendMessage,
    SendPhoto,
    UnbanChatMember,
)
from aiogram.types import (  # noqa: E402
    ChatFullInfo,
    ChatMemberAdministrator,
    ChatMemberBanned,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberRestricted,
    Message,
    Update,
    User,
)

from feurgestion.config import load_config  # noqa: E402
from feurgestion.db import Database  # noqa: E402
from feurgestion.handlers import events, info, moderation, welcome  # noqa: E402
from feurgestion.middlewares import TrackerMiddleware  # noqa: E402
from feurgestion.utils import format_duration, parse_duration  # noqa: E402

CHAT = -1003940270802
ADMIN = {"id": 8925708293, "is_bot": False, "first_name": "Flo", "username": "flo"}
VICTIM = {"id": 111111, "is_bot": False, "first_name": "Victime", "username": "victim"}
RANDOM = {"id": 333333, "is_bot": False, "first_name": "Random"}
GROUP_ADMIN = {"id": 444444, "is_bot": False, "first_name": "Modo"}
NOUSER = {"id": 555555, "is_bot": False, "first_name": "Sans", "last_name": "Pseudo"}
MEMBER_KINDS = {"member": ChatMemberMember, "administrator": ChatMemberAdministrator,
                "restricted": ChatMemberRestricted, "kicked": ChatMemberBanned, "left": ChatMemberLeft}
ALLOWED_TAGS = {"b", "i", "u", "s", "a", "code", "pre", "tg-emoji", "blockquote", "strong", "em", "tg-spoiler"}


class StrictHTML(HTMLParser):
    """Vérifie que le HTML envoyé serait accepté par Telegram (balises connues et bien fermées)."""

    def __init__(self):
        super().__init__()
        self.stack = []

    def handle_starttag(self, tag, attrs):
        assert tag in ALLOWED_TAGS, f"balise interdite <{tag}>"
        self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack.pop() == tag, f"balise mal fermée </{tag}>"


def check_html(text):
    parser = StrictHTML()
    parser.feed(text)
    parser.close()
    assert not parser.stack, f"balises non fermées : {parser.stack}"


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.status = {GROUP_ADMIN["id"]: "administrator"}
        self.users = {u["id"]: u for u in (ADMIN, VICTIM, RANDOM, GROUP_ADMIN, NOUSER)}

    def of(self, kind):
        return [c for c in self.calls if isinstance(c, kind)]

    def member(self, user_id):
        user = self.users.get(user_id, {"id": user_id, "is_bot": user_id == 9006812840, "first_name": f"U{user_id}"})
        status = self.status.get(user_id, "member")
        data = {"status": status, "user": user}
        if status == "administrator":
            for name, field in ChatMemberAdministrator.model_fields.items():
                if field.is_required() and name not in data:
                    data[name] = name not in ("can_be_edited", "is_anonymous")
        if status == "restricted":
            perms = {k: False for k in ChatMemberRestricted.model_fields if k.startswith("can_")}
            data.update(perms, is_member=True, until_date=0)
        if status == "kicked":
            data["until_date"] = 0
        return data

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        now = int(time.time())
        if isinstance(method, GetMe):
            return User(id=9006812840, is_bot=True, first_name="FeurBot", username="feurzizibot")
        if isinstance(method, GetChatMember):
            data = self.member(method.user_id)
            return MEMBER_KINDS[data["status"]].model_validate(data)
        if isinstance(method, (SendMessage, SendPhoto)):
            check_html(method.text if isinstance(method, SendMessage) else (method.caption or ""))
            return Message(message_id=99, date=now, chat={"id": method.chat_id, "type": "supergroup"}, text="ok")
        if isinstance(method, EditMessageText):
            check_html(method.text)
            return Message(message_id=method.message_id, date=now, chat={"id": method.chat_id, "type": "supergroup"}, text="ok")
        if isinstance(method, (DeleteMessages, AnswerCallbackQuery)):
            return True
        if isinstance(method, ForwardMessage):
            return Message(message_id=98, date=now, chat={"id": method.chat_id, "type": "private"}, text="fwd")
        if isinstance(method, BanChatMember):
            self.status[method.user_id] = "kicked"
            return True
        if isinstance(method, UnbanChatMember):
            if self.status.get(method.user_id) == "kicked":
                self.status[method.user_id] = "left"
            return True
        if isinstance(method, RestrictChatMember):
            self.status[method.user_id] = "member" if method.permissions.can_send_messages else "restricted"
            return True
        if isinstance(method, GetChat):
            return ChatFullInfo(
                id=CHAT, type="supergroup", title="ꜰᴇᴜʀᴄʜᴀᴛ", accent_color_id=6, max_reaction_count=11,
                accepted_gift_types={"unlimited_gifts": False, "limited_gifts": False,
                                     "unique_gifts": False, "premium_subscription": False, "gifts_from_channels": False},
                permissions={"can_send_messages": True, "can_send_photos": True, "can_invite_users": True},
            )
        if isinstance(method, GetChatMemberCount):
            return 42
        raise AssertionError(f"appel API inattendu : {type(method).__name__}")

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        raise NotImplementedError


async def main():
    # --- Durées ---
    assert parse_duration("1m") == 60
    assert parse_duration("1h") == 3600
    assert parse_duration("1d") == parse_duration("1j") == 86400
    assert parse_duration("1h30m") == 5400
    assert parse_duration("2W") == 2 * 604800
    assert parse_duration("spam") is None and parse_duration("10") is None
    assert format_duration(5400) == "1h 30min" and format_duration(None) == "définitif"

    cfg = load_config()
    assert cfg.chat_id == CHAT and cfg.log_chat_id == ADMIN["id"]

    db = Database(cfg.db_path)
    await db.connect()
    session = FakeSession()

    bot = Bot("9006812840:TEST", session=session, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(cfg=cfg, db=db)
    dp.message.outer_middleware(TrackerMiddleware(db, cfg))
    dp.include_routers(moderation.router, info.router, welcome.router, events.router)
    used = dp.resolve_used_update_types()
    assert {"message", "chat_member", "my_chat_member", "callback_query"} <= set(used), used

    counter = iter(range(1, 10_000))

    async def send(user, text=None, chat=CHAT, reply_to=None, **extra):
        n = next(counter)
        msg = {"message_id": n, "date": int(time.time()), "from": user,
               "chat": {"id": chat, "type": "supergroup" if chat == CHAT else "private", "title": "feurchat"}}
        if text is not None:
            msg["text"] = text
        if reply_to:
            msg["reply_to_message"] = reply_to
        msg.update(extra)
        session.calls.clear()
        await dp.feed_update(bot, Update(update_id=n, message=msg))
        return msg

    def replies():
        return [c.text for c in session.of(SendMessage)]

    def undo_button():
        markups = [c.reply_markup for c in session.of(SendMessage) if c.reply_markup]
        assert len(markups) == 1, "il faut exactement un bouton Annuler"
        button = markups[0].inline_keyboard[0][0]
        assert "Annuler" in button.text
        return button.callback_data

    async def click(user, data):
        n = next(counter)
        session.calls.clear()
        await dp.feed_update(bot, Update(update_id=n, callback_query={
            "id": str(n), "from": user, "chat_instance": "ci", "data": data,
            "message": {"message_id": 500, "date": int(time.time()), "text": "🔨 Ban",
                        "chat": {"id": CHAT, "type": "supergroup", "title": "feurchat"},
                        "from": {"id": 9006812840, "is_bot": True, "first_name": "FeurBot"}},
        }))

    # Une victime écrit : elle est mémorisée
    victim_msg = await send(VICTIM, "salut tout le monde")
    assert (await db.find_by_username("@VICTIM"))["user_id"] == VICTIM["id"]

    # Un non-admin ne peut rien faire
    await send(RANDOM, ".ban @victim")
    assert not session.of(BanChatMember), "un non-admin a pu bannir"

    # Ban temporaire par @pseudo
    await send(ADMIN, ".ban @victim 1h pub en masse")
    ban = session.of(BanChatMember)[0]
    assert ban.user_id == VICTIM["id"] and abs(ban.until_date - (time.time() + 3600)) < 5
    texts = replies()
    assert any("Ban" in t and "pub en masse" in t and "1h" in t for t in texts), texts
    assert any(t.startswith("#BAN #id111111") for t in texts), "pas de log envoyé à l'admin"
    assert undo_button().startswith("undo:") and not session.of(DeleteMessages), "le ban ne doit rien supprimer"

    # Déban (alias .deban)
    await send(ADMIN, ".deban 111111")
    assert session.of(UnbanChatMember) and session.status[VICTIM["id"]] == "left"

    # Mute en réponse à un message : preuve transférée dans les logs, PUIS commande + message visé supprimés
    cmd = await send(ADMIN, ".mute 30m flood", reply_to=victim_msg)
    restrict = session.of(RestrictChatMember)[0]
    assert restrict.user_id == VICTIM["id"] and not restrict.permissions.can_send_messages
    assert session.of(ForwardMessage), "le message visé n'a pas été transféré dans les logs"
    deleted = session.of(DeleteMessages)
    assert deleted and deleted[0].message_ids == [cmd["message_id"], victim_msg["message_id"]], deleted
    assert session.calls.index(session.of(ForwardMessage)[0]) < session.calls.index(deleted[0]), "preuve après suppression"
    confirm = [c for c in session.of(SendMessage) if c.chat_id == CHAT][-1]
    assert "30min" in confirm.text and "flood" in confirm.text and confirm.reply_parameters is None
    assert undo_button().startswith("undo:")

    # Mute en réponse au message de quelqu'un d'autre que la cible : on ne supprime que la commande
    other_msg = await send(RANDOM, "message innocent")
    cmd = await send(ADMIN, ".mute @victim 1h", reply_to=other_msg)
    assert session.of(DeleteMessages)[0].message_ids == [cmd["message_id"]]

    # Durée invalide
    await send(ADMIN, ".mute @victim 10s")
    assert not session.of(RestrictChatMember) and any("30s et 366j" in t for t in replies())

    # Démute (alias .demute) : droits par défaut du groupe
    await send(ADMIN, ".demute @victim")
    assert session.of(RestrictChatMember)[0].permissions.can_send_messages

    # Unmute alors qu'il n'est plus mute
    await send(ADMIN, ".unmute @victim")
    assert not session.of(RestrictChatMember) and any("pas mute" in t for t in replies())

    # Mute définitif (sans durée ni raison) : seule la commande est supprimée
    cmd = await send(ADMIN, ".MUTE @victim")
    assert session.of(RestrictChatMember)[0].until_date is None
    assert session.of(DeleteMessages)[0].message_ids == [cmd["message_id"]]
    assert any("définitif" in t and "Raison : aucune" in t for t in replies())
    await send(ADMIN, "!kick @victim relou")
    assert session.of(BanChatMember) and session.of(UnbanChatMember)
    assert not any(c.reply_markup for c in session.of(SendMessage)), "pas de bouton Annuler sur un kick"

    # On ne touche pas aux admins
    await send(ADMIN, ".ban 444444")
    assert not session.of(BanChatMember) and any("admin du groupe" in t for t in replies())
    await send(ADMIN, ".mute @flo 1h")
    assert not session.of(RestrictChatMember)

    # Sans cible
    await send(ADMIN, ".ban")
    assert any("Usage" in t for t in replies())

    # Pseudo inconnu
    await send(ADMIN, ".ban @inconnu")
    assert any("Je ne connais pas" in t for t in replies())

    # Mention sans pseudo (text_mention)
    await send(ADMIN, ".mute Sans Pseudo 1h spam", entities=[{"type": "text_mention", "offset": 6, "length": 11, "user": NOUSER}])
    restrict = session.of(RestrictChatMember)[0]
    assert restrict.user_id == NOUSER["id"] and abs(restrict.until_date - (time.time() + 3600)) < 5

    # .info : fiche + historique
    await send(VICTIM, "je suis sage")
    await send(ADMIN, ".info @victim")
    fiche = "\n".join(replies())
    assert "Bans : 1" in fiche and "Mutes : 3" in fiche and "Kicks : 1" in fiche, fiche
    assert "Messages : 2" in fiche and "pub en masse" in fiche, fiche

    # .info par ID d'un inconnu, puis sur soi-même
    await send(ADMIN, ".info 222222")
    assert "<code>222222</code>" in "\n".join(replies())
    await send(ADMIN, ".info")
    assert "<code>8925708293</code>" in "\n".join(replies())

    # Bouton Annuler sur un ban définitif sans raison
    await send(ADMIN, ".ban @victim")
    assert any("définitif" in t and "Raison : aucune" in t for t in replies())
    data = undo_button()
    await click(RANDOM, data)
    assert session.of(AnswerCallbackQuery)[0].show_alert and not session.of(UnbanChatMember), "un non-admin a annulé"
    await click(ADMIN, data)
    assert session.of(UnbanChatMember) and session.status[VICTIM["id"]] == "left"
    edit = session.of(EditMessageText)[0]
    assert "Annulé" in edit.text and edit.reply_markup is None
    assert "annulation du ban" in (await db.last_action(VICTIM["id"], "unban"))["reason"]
    assert any(t.startswith("#UNBAN") for t in replies()), "pas de log de l'annulation"

    # Bouton Annuler sur un mute
    await send(ADMIN, ".mute @victim 1h")
    await click(ADMIN, undo_button())
    assert session.of(RestrictChatMember)[0].permissions.can_send_messages

    # .logs
    await send(ADMIN, ".logs")
    assert "dernières sanctions" in replies()[0] and "Victime" in replies()[0]

    # .help (aussi en privé)
    await send(ADMIN, ".help", chat=ADMIN["id"])
    assert "FeurGestion" in replies()[0]
    await send(ADMIN, "/start", chat=ADMIN["id"])
    assert "logs ici" in replies()[0]

    # Admin anonyme
    await send({"id": 1087968824, "is_bot": True, "first_name": "Group", "username": "GroupAnonymousBot"},
               ".ban @victim", sender_chat={"id": CHAT, "type": "supergroup", "title": "feurchat"})
    assert any("mode anonyme" in t for t in replies())

    # Message de bienvenue : texte avec mise en forme et variables
    await send(ADMIN, ".welcome Yo {mention} sur {chat} ({count} membres)",
               entities=[{"type": "bold", "offset": 9, "length": 2}])
    preview = replies()[0]
    assert "<b>Yo</b>" in preview and "ꜰᴇᴜʀᴄʜᴀᴛ" in preview and "42 membres" in preview, preview
    assert (await welcome.get_welcome(db))["text"].startswith("<b>Yo</b>")

    # Photo avec légende .welcome
    await send(ADMIN, None, photo=[{"file_id": "PHOTO_S", "file_unique_id": "s", "width": 90, "height": 90},
                                   {"file_id": "PHOTO_L", "file_unique_id": "l", "width": 800, "height": 800}],
               caption=".welcome Bienvenue {name} !")
    photo = session.of(SendPhoto)[0]
    assert photo.photo == "PHOTO_L" and photo.caption == "Bienvenue Flo !"

    # Texte seul : garde la photo
    await send(ADMIN, ".welcome Salut {username}")
    assert session.of(SendPhoto)[0].caption == "Salut @flo"

    # Arrivée d'un membre -> bienvenue avec photo dans le groupe + journal
    newbie = {"id": 666666, "is_bot": False, "first_name": "Nouveau", "username": "newbie"}
    session.calls.clear()
    await dp.feed_update(bot, Update(update_id=next(counter), chat_member={
        "chat": {"id": CHAT, "type": "supergroup", "title": "feurchat"}, "from": newbie, "date": int(time.time()),
        "old_chat_member": {"status": "left", "user": newbie},
        "new_chat_member": {"status": "member", "user": newbie},
        "invite_link": {"invite_link": "https://t.me/+abc", "creator": ADMIN, "creates_join_request": False,
                        "is_primary": False, "is_revoked": False, "name": "Lien TikTok"},
    }))
    photo = session.of(SendPhoto)[0]
    assert photo.chat_id == CHAT and photo.caption == "Salut @newbie"
    join = await db.last_action(666666, "join")
    assert join and "Lien TikTok" in join["reason"]

    # Désactivation
    await send(ADMIN, ".welcome off")
    assert not (await welcome.get_welcome(db))["enabled"]

    # Ban fait à la main par un autre admin -> journalisé + log
    modo = {"id": GROUP_ADMIN["id"], "is_bot": False, "first_name": "Modo"}
    session.calls.clear()
    await dp.feed_update(bot, Update(update_id=next(counter), chat_member={
        "chat": {"id": CHAT, "type": "supergroup", "title": "feurchat"}, "from": modo, "date": int(time.time()),
        "old_chat_member": {"status": "member", "user": newbie},
        "new_chat_member": {"status": "kicked", "user": newbie, "until_date": 0},
    }))
    assert await db.last_action(666666, "ban")
    assert any("fait à la main" in t for t in replies())

    # Départ volontaire -> journal seulement
    session.calls.clear()
    await dp.feed_update(bot, Update(update_id=next(counter), chat_member={
        "chat": {"id": CHAT, "type": "supergroup", "title": "feurchat"}, "from": VICTIM, "date": int(time.time()),
        "old_chat_member": {"status": "member", "user": VICTIM},
        "new_chat_member": {"status": "left", "user": VICTIM},
    }))
    assert await db.last_action(VICTIM["id"], "leave") and not session.of(SendMessage)

    # Le bot devient admin -> prévient l'admin
    session.calls.clear()
    botuser = {"id": 9006812840, "is_bot": True, "first_name": "FeurBot", "username": "feurzizibot"}
    await dp.feed_update(bot, Update(update_id=next(counter), my_chat_member={
        "chat": {"id": CHAT, "type": "supergroup", "title": "feurchat"}, "from": ADMIN, "date": int(time.time()),
        "old_chat_member": {"status": "member", "user": botuser},
        "new_chat_member": {**session.member(GROUP_ADMIN["id"]), "user": botuser},
    }))
    assert any("Je suis admin" in t for t in replies())

    # Changement de pseudo : l'ancien reste retrouvable et apparaît dans .info
    renamed = {**VICTIM, "username": "victim2", "first_name": "Nouveau nom"}
    session.users[VICTIM["id"]] = renamed
    await send(renamed, "j'ai changé")
    assert (await db.find_by_username("victim"))["user_id"] == VICTIM["id"]
    await send(ADMIN, ".info @victim2")
    fiche = "\n".join(replies())
    assert "Historique des pseudos" in fiche and "@victim2 — actuel" in fiche and "@victim — du" in fiche, fiche
    assert "Historique des noms" in fiche and "Nouveau nom — actuel" in fiche and "Victime — du" in fiche, fiche

    print("✅ Tous les tests passent")


async def run():
    try:
        await main()
    finally:
        for task in asyncio.all_tasks() - {asyncio.current_task()}:
            task.cancel()


# aiosqlite garde un thread ouvert si un test échoue : on force la sortie
exit_code = 0
try:
    asyncio.run(run())
except BaseException:
    traceback.print_exc()
    exit_code = 1
sys.stdout.flush()
sys.stderr.flush()
os._exit(exit_code)
