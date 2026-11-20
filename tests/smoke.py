"""Test de bout en bout sans réseau : on simule l'API Telegram et on envoie de faux messages au bot.

Lancer : python tests/smoke.py
"""

import asyncio
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.update(BOT_TOKEN="9006812840:TEST", CHAT_ID="3940270802", ADMIN_IDS="8925708293")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from aiogram import Bot  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.methods import (  # noqa: E402
    AnswerCallbackQuery,
    BanChatMember,
    DeleteMessage,
    DeleteMessages,
    EditMessageText,
    ForwardMessage,
    GetChat,
    GetChatAdministrators,
    GetChatMember,
    GetChatMemberCount,
    GetMe,
    PinChatMessage,
    RestrictChatMember,
    SendDice,
    SendMessage,
    SendPhoto,
    SetChatPermissions,
    UnbanChatMember,
    UnpinChatMessage,
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
    UserProfilePhotos,
)

from feurbot import utils  # noqa: E402
from feurbot.app import build_dispatcher  # noqa: E402
from feurbot.config import load_config  # noqa: E402
from feurbot.db import Database  # noqa: E402
from feurbot import commands  # noqa: E402
from feurbot.handlers import fun, games, memory, passive, welcome  # noqa: E402
from feurbot.handlers import help as help_module  # noqa: E402
from feurbot.jokes import EIGHTBALL, HACK_STEPS, JOKES, QUOI_ANSWERS, QUIPS, analyze, feur_reply  # noqa: E402
from feurbot.utils import format_duration, parse_duration  # noqa: E402

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
        self.permissions = {"can_send_messages": True, "can_send_photos": True, "can_send_videos": True,
                            "can_send_polls": True, "can_invite_users": True}

    def of(self, kind):
        return [c for c in self.calls if isinstance(c, kind)]

    def member(self, user_id, status=None):
        user = self.users.get(user_id, {"id": user_id, "is_bot": user_id == 9006812840, "first_name": f"U{user_id}"})
        status = status or self.status.get(user_id, "member")
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
        result = await self._respond(bot, method)
        # Comme la vraie session : les objets renvoyés sont rattachés au bot
        return result.as_(bot) if isinstance(result, Message) else result

    async def _respond(self, bot, method):
        self.calls.append(method)
        now = int(time.time())
        if isinstance(method, GetMe):
            return User(id=9006812840, is_bot=True, first_name="FeurBot", username="feurzizibot")
        if isinstance(method, GetChatMember):
            data = self.member(method.user_id)
            return MEMBER_KINDS[data["status"]].model_validate(data)
        if type(method).__name__.startswith("Send"):
            check_html(getattr(method, "text", None) or getattr(method, "caption", None) or "")
            return Message(message_id=99, date=now, chat={"id": method.chat_id, "type": "supergroup"}, text="ok")
        if isinstance(method, GetChatAdministrators):
            return [MEMBER_KINDS["administrator"].model_validate(self.member(uid, "administrator"))
                    for uid in (ADMIN["id"], GROUP_ADMIN["id"])]
        if isinstance(method, SetChatPermissions):
            self.permissions = method.permissions.model_dump(exclude_none=True)
            return True
        if type(method).__name__ in ("SetMessageReaction", "SetMyCommands", "DeleteMyCommands"):
            return True
        if type(method).__name__ == "GetUserProfilePhotos":
            return UserProfilePhotos(total_count=0, photos=[])
        if type(method).__name__ == "EditMessageMedia":
            return Message(message_id=method.message_id, date=now, chat={"id": method.chat_id, "type": "supergroup"}, text="ok")
        if isinstance(method, (DeleteMessage, PinChatMessage, UnpinChatMessage)):
            return True
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
                permissions=self.permissions,
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

    db = Database(cfg.db_path, cfg.tz)
    await db.connect()
    session = FakeSession()

    bot = Bot("9006812840:TEST", session=session, default=DefaultBotProperties(parse_mode="HTML"))
    dp = build_dispatcher(cfg, db)
    await db.set_setting("motinterdit_on", False)
    passive.EASTER_EGG_CHANCE = 0
    fun.HACK_DELAY = 0
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
        assert "Annuler" in button.text or "Retirer" in button.text
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
    cmd = await send(ADMIN, ".ban @victim 1h pub en masse")
    ban = session.of(BanChatMember)[0]
    assert ban.user_id == VICTIM["id"] and abs(ban.until_date - (time.time() + 3600)) < 5
    texts = replies()
    assert any("Ban" in t and "pub en masse" in t and "1h" in t for t in texts), texts
    assert any(t.startswith("#BAN #id111111") for t in texts), "pas de log envoyé à l'admin"
    assert undo_button().startswith("undo:")
    assert session.of(DeleteMessages)[0].message_ids == [cmd["message_id"]], "la commande .ban doit être supprimée"

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

    # Ban définitif sans raison, en réponse : preuve transférée puis commande + message visé supprimés
    pub = await send(VICTIM, "rejoignez mon canal")
    cmd = await send(ADMIN, ".ban", reply_to=pub)
    deleted = session.of(DeleteMessages)
    assert deleted and deleted[0].message_ids == [cmd["message_id"], pub["message_id"]], deleted
    assert session.calls.index(session.of(ForwardMessage)[0]) < session.calls.index(deleted[0]), "preuve après suppression"
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
    assert "FeurBot" in replies()[0]
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
    assert (await welcome.get_welcome(db))["texts"] == ["<b>Yo</b> {mention} sur {chat} ({count} membres)"]

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

    # ================= Fonctions FeurBot =================
    def texts():
        return [getattr(c, "text", None) or getattr(c, "caption", None) or "" for c in session.calls
                if type(c).__name__.startswith("Send") or isinstance(c, EditMessageText)]

    # --- quoi -> feur ---
    assert feur_reply("c'est quoi ???") is not None and feur_reply("QUOIII 😂") is not None
    assert feur_reply("bonjour") is None and feur_reply("") is None
    utils._cooldowns.clear()
    await send(RANDOM, "tu fais quoi ?")
    assert any(t in QUOI_ANSWERS for t in replies()), replies()
    assert any(type(c).__name__ == "SetMessageReaction" and c.reaction[0].emoji == "🤡" for c in session.calls)
    await send(RANDOM, "et toi tu dis quoi")
    assert not replies(), "le cooldown feur ne marche pas"
    await send(ADMIN, ".feur off")
    utils._cooldowns.clear()
    await send(RANDOM, "quoi")
    assert not replies(), "feur désactivé mais répond quand même"
    await send(ADMIN, ".feur on")

    # --- Un non-admin qui joue au chef ---
    utils._cooldowns.clear()
    await send(RANDOM, ".warn @victim")
    assert replies() and replies()[0] in QUIPS["not_admin"]
    await send(RANDOM, ".lock liens")
    assert not replies(), "pas de spam de répliques (cooldown)"

    # --- Warns ---
    session.status[VICTIM["id"]] = "member"
    await send(ADMIN, ".warn @victim2 spam")
    assert "Warn 1/3" in replies()[0]
    first_warn = undo_button()
    assert first_warn.startswith("unwarn:")
    await send(ADMIN, ".warn @victim2 flood")
    assert "Warn 2/3" in replies()[0]
    await click(ADMIN, first_warn)
    assert "Warn retiré" in session.of(EditMessageText)[0].text
    await send(RANDOM, ".warns @victim2")
    assert "1/3" in replies()[0] and "flood" in replies()[0]
    await send(ADMIN, ".warnlimit 2")
    await send(ADMIN, ".warnaction ban")
    await send(ADMIN, ".warn @victim2 encore")
    assert session.of(BanChatMember) and "automatique" in replies()[0], replies()
    assert not await db.user_warns(VICTIM["id"]), "compteur pas remis à zéro"
    session.status[VICTIM["id"]] = "member"
    await send(ADMIN, ".warn @victim2 test")
    await send(ADMIN, ".unwarn @victim2")
    assert "retiré" in replies()[0] and not await db.user_warns(VICTIM["id"])
    await send(ADMIN, ".warnlimit 3")
    await send(ADMIN, ".warnaction mute")

    # --- Notes ---
    await send(ADMIN, ".save bienvenue Salut {name} !")
    assert "#bienvenue" in replies()[0]
    await send(RANDOM, "#bienvenue")
    assert "Salut Random !" in replies()
    photo_msg = await send(ADMIN, None, photo=[{"file_id": "NOTE_PIC", "file_unique_id": "n", "width": 9, "height": 9}],
                           caption="regardez ça")
    await send(ADMIN, ".save image", reply_to=photo_msg)
    await send(RANDOM, ".get image")
    assert session.of(SendPhoto)[0].photo == "NOTE_PIC" and session.of(SendPhoto)[0].caption == "regardez ça"
    await send(RANDOM, ".notes")
    assert "#bienvenue" in replies()[0] and "#image" in replies()[0]
    await send(ADMIN, ".clear bienvenue")
    await send(RANDOM, "#bienvenue")
    assert not replies()

    # --- Filtres ---
    await send(ADMIN, '.filter "bonne nuit" Dors bien {mention} 😴',
               entities=[{"type": "bold", "offset": 21, "length": 9}])
    assert "bonne nuit" in replies()[0]
    await send(RANDOM, "allez Bonne Nuit les gens")
    assert any(t.startswith("<b>Dors bien</b>") and "Random" in t for t in replies()), replies()
    await send(RANDOM, "bonne nuitée")
    assert not replies(), "le filtre ne doit matcher que le mot entier"
    await send(ADMIN, '.stop "bonne nuit"')
    await send(RANDOM, "bonne nuit")
    assert not any("Dors bien" in t for t in replies())

    # --- Règles ---
    await send(RANDOM, ".rules")
    assert "anarchie" in replies()[0]
    await send(ADMIN, ".setrules 1. Pas de pub\n2. On ne dit pas quoi")
    await send(RANDOM, ".regles")
    assert "Pas de pub" in replies()[0]

    # --- Verrous ---
    await send(ADMIN, ".lock liens")
    utils._cooldowns.clear()
    await send(RANDOM, "rejoins https://spam.example/promo")
    assert session.of(DeleteMessage), "le lien n'a pas été supprimé"
    assert any("PUB = MUTE" in t for t in replies())
    await send(RANDOM, "mon canal : t.me/moncanal")
    assert session.of(DeleteMessage), "lien t.me sans http pas détecté"
    await send(GROUP_ADMIN, "lien officiel https://feurchat.fr")
    assert not session.of(DeleteMessage), "un admin s'est fait supprimer son lien"
    await send(ADMIN, ".lock transferts")
    await send(RANDOM, "regardez", forward_origin={"type": "hidden_user", "date": int(time.time()), "sender_user_name": "x"})
    assert session.of(DeleteMessage)
    await send(ADMIN, ".lock medias")
    perms = session.of(SetChatPermissions)[0].permissions
    assert perms.can_send_photos is False and perms.can_send_videos is False and perms.can_send_messages is True
    assert perms.can_send_polls is True, "un verrou a écrasé d'autres droits"
    await send(ADMIN, ".locks")
    assert "🔒 <code>medias</code>" in replies()[0] and "🔒 <code>liens</code>" in replies()[0]
    await send(ADMIN, ".unlock medias")
    assert session.of(SetChatPermissions)[0].permissions.can_send_photos is True
    await send(ADMIN, ".unlock liens")
    await send(ADMIN, ".unlock transferts")
    await send(RANDOM, "https://ok.example")
    assert not session.of(DeleteMessage)

    # --- AFK ---
    utils._cooldowns.clear()
    await send(NOUSER, ".afk dodo")
    assert "AFK" in replies()[0] and "dodo" in replies()[0]
    nouser_msg = await send(NOUSER, ".afk dodo")  # la commande elle-même ne compte pas comme un retour
    assert await db.get_afk(NOUSER["id"])
    await send(RANDOM, "t'es là ?", reply_to=nouser_msg)
    assert any("est AFK depuis" in t and "dodo" in t for t in replies()), replies()
    await send(NOUSER, "me revoilà")
    assert any(t.startswith("👋 Re") for t in replies()) and not await db.get_afk(NOUSER["id"])
    await send(RANDOM, "brb je mange")
    assert (await db.get_afk(RANDOM["id"]))["reason"] == "je mange"
    await send(RANDOM, "fini")
    assert not await db.get_afk(RANDOM["id"])

    # --- Outils ---
    spam = await send(RANDOM, "spam 1")
    await send(RANDOM, "spam 2")
    cmd = await send(ADMIN, ".purge", reply_to=spam)
    assert session.of(DeleteMessages)[0].message_ids == list(range(spam["message_id"], cmd["message_id"] + 1))
    await send(ADMIN, ".pin silence", reply_to=spam)
    assert session.of(PinChatMessage)[0].disable_notification is True
    await send(ADMIN, ".unpin")
    assert session.of(UnpinChatMessage)
    await send(RANDOM, ".id", reply_to=spam)
    assert f"<code>{RANDOM['id']}</code>" in replies()[0] and f"<code>{CHAT}</code>" in replies()[0]
    await send(RANDOM, ".ping")
    assert "Pong !" in session.of(EditMessageText)[0].text
    utils._cooldowns.clear()
    await send(NOUSER, ".report", reply_to=spam)
    assert any(t.startswith("#REPORT") for t in replies()) and session.of(ForwardMessage)
    await send(VICTIM, "@admin regardez ça", reply_to=spam)
    assert any(t.startswith("#REPORT") for t in replies()), "@admin n'a pas déclenché de signalement"

    # --- Fun ---
    utils._cooldowns.clear()
    await send(RANDOM, ".blague")
    assert replies()[0].removeprefix("😂 ") in JOKES
    await send(NOUSER, ".de")
    assert session.of(SendDice)[0].emoji == "🎲"
    await send(VICTIM, ".boule je vais être admin ?")
    assert replies()[0].removeprefix("🎱 ") in EIGHTBALL
    await send(VICTIM, ".blague")
    assert not replies(), "anti-spam des commandes fun"

    # --- Aide ---
    await send(ADMIN, ".help")
    menu = session.of(SendMessage)[0]
    assert "FeurBot" in menu.text and menu.reply_markup.inline_keyboard
    await click(RANDOM, "help:jeux")
    assert "/flocko" in session.of(EditMessageText)[0].text
    await click(RANDOM, "help:warns")
    assert session.of(AnswerCallbackQuery)[0].show_alert and not session.of(EditMessageText), "rubrique staff visible"
    await send(RANDOM, "/aide")
    member_menu = session.of(SendMessage)[0]
    assert "membre" in member_menu.text and len(sum(member_menu.reply_markup.inline_keyboard, [])) == 4
    await send(RANDOM, "/help duel")
    assert "/duel" in replies()[0] and "Aide pour /duel" in replies()[0]
    await send(RANDOM, "/help ban")
    assert "Je ne connais pas" in replies()[0], "un membre ne doit pas voir l'aide des commandes staff"

    # --- Annonce des changements de pseudo ---
    await send(ADMIN, ".sangmata on")
    newer = {**RANDOM, "username": "random_le_vrai"}
    session.users[RANDOM["id"]] = newer
    await send(newer, "salut")
    assert any("Changement d'identité" in t and "@random_le_vrai" in t for t in replies()), replies()
    await send(ADMIN, ".sangmata off")

    # --- Modos ---
    MOD = NOUSER
    utils._cooldowns.clear()
    await send(RANDOM, ".mod 555555")
    assert replies() and replies()[0] in QUIPS["not_admin"] and not await db.is_mod(MOD["id"])
    await send(ADMIN, ".mod 555555")
    assert "est maintenant modo" in replies()[0] and any(t.startswith("#MOD") for t in replies())
    assert await db.is_mod(MOD["id"])
    await send(ADMIN, ".mod 555555")
    assert "déjà modo" in replies()[0]
    await send(ADMIN, ".mod @flo")
    assert "déjà admin" in replies()[0]

    # Le modo peut sanctionner, avec bouton Annuler
    session.status[VICTIM["id"]] = "member"
    await send(MOD, ".mute @victim2 1h spam")
    assert session.of(RestrictChatMember) and session.of(RestrictChatMember)[0].user_id == VICTIM["id"]
    mute_button = undo_button()
    await click(RANDOM, mute_button)
    assert session.of(AnswerCallbackQuery)[0].show_alert and not session.of(RestrictChatMember)
    await click(MOD, mute_button)
    assert session.of(RestrictChatMember)[0].permissions.can_send_messages, "le modo n'a pas pu annuler"
    await send(MOD, ".warn @victim2 test modo")
    assert "Warn 1/3" in replies()[0]
    await send(MOD, ".resetwarns @victim2")
    await send(MOD, ".info @victim2")
    assert "Fiche utilisateur" in replies()[0]

    # ... mais pas un admin, ni un autre modo, ni la config
    await send(MOD, ".mute 8925708293 1h")
    assert not session.of(RestrictChatMember) and "admin du bot" in replies()[0]
    await send(ADMIN, f".mod {RANDOM['id']}")
    await send(MOD, f".mute {RANDOM['id']} 1h")
    assert not session.of(RestrictChatMember) and "modo, comme toi" in replies()[0]
    await send(ADMIN, f".mute {RANDOM['id']} 1h")
    assert session.of(RestrictChatMember), "un admin doit pouvoir sanctionner un modo"
    await send(ADMIN, f".unmod {RANDOM['id']}")
    assert "n'est plus modo" in replies()[0]
    utils._cooldowns.clear()
    await send(MOD, ".lock liens")
    assert "T'es modo" in replies()[0] and not await db.get_setting("locks", [])

    # Les verrous ne touchent pas les modos
    await send(ADMIN, ".lock liens")
    await send(MOD, "le site officiel : https://feurchat.example")
    assert not session.of(DeleteMessage), "le lien d'un modo a été supprimé"
    await send(ADMIN, ".unlock liens")

    # Aide, équipe et fiche
    await send(MOD, ".help")
    menu = session.of(SendMessage)[0]
    assert "modo" in menu.text and len(sum(menu.reply_markup.inline_keyboard, [])) == 7
    await send(VICTIM, ".mods")
    assert "Sans Pseudo" in replies()[0] and "Admins" in replies()[0]
    await send(ADMIN, ".info 555555")
    assert "Rôle : 🛡 Modo" in replies()[0] and "Nommé modo" in replies()[0]

    # Retrait
    await send(ADMIN, ".unmod 555555")
    assert "n'est plus modo" in replies()[0] and any(t.startswith("#UNMOD") for t in replies())
    utils._cooldowns.clear()
    await send(MOD, ".mute @victim2 1h")
    assert not session.of(RestrictChatMember) and replies()[0] in QUIPS["not_admin"]
    await send(ADMIN, ".unmod 555555")
    assert "n'est pas modo" in replies()[0]

    # ================= Fonctions fun (v3) =================
    utils._cooldowns.clear()

    # --- Les petits malins du feur ---
    assert analyze("quoi (pas de feur)").answer == "Bien essayé. Feur. 😏"
    assert analyze("ok feur").answer.startswith("Tu fais mon travail")
    assert analyze("mdr t'es nul").reaction == "🤣"
    assert analyze("hein").answer in ("deux", "apagnan", None)
    assert "quoicoubeh" in QUOI_ANSWERS

    # --- Feurboard et titres ---
    for _ in range(9):
        await db.add_feur(VICTIM["id"])
    await send(VICTIM, "c'est quoi")
    assert any("Victime certifiée" in t for t in replies()), replies()
    await send(NOUSER, "/feurboard")
    assert "Feurboard" in replies()[0] and "10 « quoi »" in replies()[0]

    # --- Toutes les commandes marchent avec / (et @nom_du_bot) ---
    utils._cooldowns.clear()
    await send(NOUSER, "/blague@feurzizibot")
    assert replies()[0].removeprefix("😂 ") in JOKES

    # --- Mot interdit du jour ---
    await db.set_setting("motinterdit_on", True)
    await db.set_setting("motinterdit", {"date": db.today(), "word": "pizza", "found_by": None})
    await send(ADMIN, ".motinterdit", chat=ADMIN["id"])
    assert "pizza" in replies()[0], "l'admin doit voir le mot en privé"
    await send(NOUSER, ".motinterdit")
    assert "pizza" not in replies()[0], "le mot ne doit pas fuiter dans le groupe"
    session.status[NOUSER["id"]] = "member"
    await send(NOUSER, "on se fait une Pizza ce soir ?")
    assert any("BOOM" in t for t in replies()) and session.of(RestrictChatMember)
    assert (await db.last_action(NOUSER["id"], "jail"))["reason"] == "mot interdit"
    await send(VICTIM, "moi aussi je veux de la pizza")
    assert not any("BOOM" in t for t in replies()), "le mot ne doit exploser qu'une fois par jour"
    await send(VICTIM, ".motinterdit")
    assert "Déjà trouvé" in replies()[0]
    await send(RANDOM, ".motinterdit off")
    assert await db.get_setting("motinterdit_on"), "un membre a désactivé le mot interdit"
    await db.set_setting("motinterdit_on", False)

    # --- Roulette ---
    games.random.randint, real_randint = (lambda a, b: 1), games.random.randint
    try:
        session.status[VICTIM["id"]] = "member"
        await send(VICTIM, "/roulette")
        assert any("PAN" in t for t in replies()) and session.of(RestrictChatMember)
        await send(ADMIN, "/roulette")
        assert any("gilet pare-balles" in t for t in replies()) and not session.of(RestrictChatMember)
    finally:
        games.random.randint = real_randint
    games.random.randint, real_randint = (lambda a, b: 4), games.random.randint
    try:
        utils._cooldowns.clear()
        await send(VICTIM, "/roulette")
        assert "clic" in replies()[0] and not session.of(RestrictChatMember)
    finally:
        games.random.randint = real_randint
    await send(NOUSER, ".jeux off")
    assert await db.get_setting("jeux", True), "un membre a coupé les jeux"
    await send(ADMIN, ".jeux off")
    utils._cooldowns.clear()
    await send(VICTIM, "/roulette")
    assert "désactivés" in replies()[0]
    await send(ADMIN, ".jeux on")

    # --- Duel ---
    utils._cooldowns.clear()
    await send(RANDOM, f"/duel {VICTIM['id']}")
    duel_data = session.of(SendMessage)[0].reply_markup.inline_keyboard[0][0].callback_data
    await click(NOUSER, duel_data)
    assert session.of(AnswerCallbackQuery)[0].show_alert and not session.of(EditMessageText)
    games.random.choice, real_choice = (lambda options: options[0]), games.random.choice
    try:
        session.status[RANDOM["id"]] = "member"
        await click(VICTIM, duel_data)
        assert session.of(RestrictChatMember)[0].user_id == RANDOM["id"], "le perdant (challenger) doit être mute"
        assert "Duel" in session.of(EditMessageText)[0].text
    finally:
        games.random.choice = real_choice
    await click(VICTIM, duel_data.replace("duel:ok:", "duel:no:"))
    assert "Poule mouillée" in session.of(EditMessageText)[0].text
    old = duel_data.rsplit(":", 1)[0] + ":1000"
    await click(VICTIM, old)
    assert "expiré" in session.of(EditMessageText)[0].text

    # --- Prison ---
    await send(VICTIM, "/prison")
    assert "haute sécurité" in replies()[0] and "🎮" in replies()[0], replies()

    # --- Tirages du jour ---
    utils._cooldowns.clear()
    await send(VICTIM, "/couple")
    first_couple = replies()[0]
    assert "Couple du jour" in first_couple
    utils._cooldowns.clear()
    await send(NOUSER, "/couple")
    assert replies()[0].split("\n")[1] == first_couple.split("\n")[1], "le couple doit rester le même toute la journée"
    utils._cooldowns.clear()
    await send(VICTIM, "/elu")
    assert "boloss du jour" in replies()[0]
    utils._cooldowns.clear()
    await send(VICTIM, f"/love {RANDOM['id']}")
    love = replies()[0]
    utils._cooldowns.clear()
    await send(VICTIM, f"/love {RANDOM['id']}")
    assert "%" in love and replies()[0] == love, "le score d'amour doit être fixe pour la journée"
    utils._cooldowns.clear()
    await send(VICTIM, "/qi")
    assert "QI de" in replies()[0]

    # --- Hack, clash, moqueur ---
    await send(VICTIM, f"/hack {RANDOM['id']}")
    edits = session.of(EditMessageText)
    assert len(edits) == len(HACK_STEPS) and "terminé" in edits[-1].text
    utils._cooldowns.clear()
    await send(VICTIM, f"/clash {RANDOM['id']}")
    assert "espèce de" in replies()[0]
    target_msg = await send(RANDOM, "tu fais quoi")
    utils._cooldowns.clear()
    await send(VICTIM, "/moqueur", reply_to=target_msg)
    assert any("tU fAiS qUoI" in t for t in replies()), replies()

    # --- Livre d'or ---
    perle = await send(RANDOM, "les pâtes à l'eau froide c'est meilleur")
    utils._cooldowns.clear()
    await send(VICTIM, "/citer", reply_to=perle)
    assert "Citation <b>#1</b>" in replies()[0]
    utils._cooldowns.clear()
    await send(VICTIM, "/citer", reply_to=perle)
    assert "Déjà" in replies()[0]
    await send(NOUSER, "/citation")
    assert "pâtes à l&#x27;eau froide" in replies()[0] and "(#1)" in replies()[0]
    await send(NOUSER, f"/citation {RANDOM['id']}")
    assert "pâtes" in replies()[0]
    await send(NOUSER, "/delcitation 1")
    assert not await db.get_quote(1) is None, "un membre a supprimé une citation"
    await send(ADMIN, "/delcitation 1")
    assert await db.get_quote(1) is None

    # --- Top des bavards ---
    await send(VICTIM, "/top")
    assert "Top des bavards" in replies()[0] and "Pipelette en chef" in replies()[0]

    # --- Anniversaires ---
    await send(VICTIM, "/anniv 31/02")
    assert "Format" in replies()[0]
    today = datetime.now(cfg.tz)
    await send(VICTIM, f"/anniv {today.day}/{today.month}")
    assert "Noté" in replies()[0]
    await send(NOUSER, "/anniversaires")
    assert "aujourd'hui" in replies()[0]
    session.calls.clear()
    await memory.wish_birthdays(bot, db, cfg)
    assert any("Joyeux anniversaire" in t for t in replies())
    session.calls.clear()
    await memory.wish_birthdays(bot, db, cfg)
    assert not replies(), "anniversaire souhaité deux fois le même jour"

    # --- Flocko ---
    await send(VICTIM, "/flocko")
    assert "Taux de flocko" in replies()[0]
    first = await db.get_flocko(VICTIM["id"])
    await send(VICTIM, ".flocko")
    assert "Prochain tirage dans" in replies()[0]
    await db.conn.execute("UPDATE flocko SET last_at = last_at - 13 * 3600, best = 0 WHERE user_id = ?", (VICTIM["id"],))
    await db.conn.commit()
    await send(VICTIM, "/flocko")
    after = await db.get_flocko(VICTIM["id"])
    assert after["rolls"] == 2 and after["best"] >= after["last"] and after["last_at"] >= first["last_at"]
    # Le record ne baisse jamais
    await db.save_flocko(VICTIM["id"], 100)
    await db.save_flocko(VICTIM["id"], 3)
    assert (await db.get_flocko(VICTIM["id"]))["best"] == 100
    for user_id in range(700000, 700014):
        session.users[user_id] = {"id": user_id, "is_bot": False, "first_name": f"Joueur {user_id % 100}"}
        await db.track_user(User(**session.users[user_id]), active=False)
        await db.save_flocko(user_id, user_id % 97)
    utils._cooldowns.clear()
    await send(NOUSER, "/topflocko")
    photo = session.of(SendPhoto)[0]
    assert photo.photo.data.startswith(b"\x89PNG") and "Top flocko" in photo.caption
    buttons = photo.reply_markup.inline_keyboard[0]
    assert buttons[0].text == "⬅️ Suivant" and buttons[0].callback_data == "flocko:2"
    await click(NOUSER, "flocko:2")
    media = [c for c in session.calls if type(c).__name__ == "EditMessageMedia"]
    assert media and media[0].media.media.data.startswith(b"\x89PNG")
    assert media[0].reply_markup.inline_keyboard[0][-1].text == "Précédent ➡️"

    # --- Menu « / » de Telegram ---
    session.calls.clear()
    await commands.sync_commands(bot, cfg, db)
    menus = [c for c in session.calls if type(c).__name__ == "SetMyCommands"]
    public = next(c for c in menus if type(c.scope).__name__ == "BotCommandScopeDefault")
    full = next(c for c in menus if type(c.scope).__name__ == "BotCommandScopeChatMember")
    assert len(full.commands) > len(public.commands) and not any(c.command == "ban" for c in public.commands)
    assert all(len(c.commands) <= 100 for c in menus)
    await send(ADMIN, f".mod {RANDOM['id']}")
    assert any(type(c).__name__ == "SetMyCommands" for c in session.calls)
    await send(ADMIN, f".unmod {RANDOM['id']}")
    assert any(type(c).__name__ == "DeleteMyCommands" for c in session.calls)

    # --- Bienvenue : variantes au hasard ---
    await send(ADMIN, ".welcome reset")
    conf = await welcome.get_welcome(db)
    assert conf["texts"] == welcome.DEFAULT_TEXTS
    await send(ADMIN, ".welcome add Coucou {name}, installe-toi !")
    assert len((await welcome.get_welcome(db))["texts"]) == len(welcome.DEFAULT_TEXTS) + 1
    await send(ADMIN, ".welcome list")
    assert "Coucou" in replies()[0]
    await send(ADMIN, ".welcome del 1")
    assert len((await welcome.get_welcome(db))["texts"]) == len(welcome.DEFAULT_TEXTS)
    picks = [welcome.pick_text(conf["texts"]) for _ in range(30)]
    assert all(a != b for a, b in zip(picks, picks[1:])), "deux fois le même message d'affilée"
    await send(ADMIN, ".welcome on")
    session.calls.clear()
    newcomer = {"id": 777777, "is_bot": False, "first_name": "Petit", "last_name": "Nouveau"}
    await dp.feed_update(bot, Update(update_id=next(counter), chat_member={
        "chat": {"id": CHAT, "type": "supergroup", "title": "feurchat"}, "from": newcomer, "date": int(time.time()),
        "old_chat_member": {"status": "left", "user": newcomer},
        "new_chat_member": {"status": "member", "user": newcomer},
    }))
    greeting = session.of(SendMessage)[0].text
    assert "Petit Nouveau" in greeting and "{" not in greeting, greeting
    # Ancien format (un seul texte personnalisé) : gardé parmi les variantes
    await db.set_setting("welcome", {"enabled": True, "text": "Yo {name}", "media_type": None, "media_id": None})
    assert "Yo {name}" in (await welcome.get_welcome(db))["texts"]

    # Tout le HTML envoyé (aide comprise) doit être valide
    for _, _, text in help_module.SECTIONS.values():
        check_html(text)
    for role in help_module.ROLES:
        check_html(help_module._menu("Flo <3", role)[0])
    for text in welcome.DEFAULT_TEXTS:
        check_html(text)

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
