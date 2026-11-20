"""Aide à boutons, /start, et répliques quand un non-admin joue au chef."""

import random
import re
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import Config
from ..db import Database
from ..filters import IsAnonymousAdmin, IsMember
from ..jokes import quip
from ..utils import PREFIXES, on_cooldown

router = Router(name="help")

# Commandes réservées aux admins (les autres sont publiques)
ADMIN_ONLY = (
    "ban", "unban", "deban", "mute", "unmute", "demute", "kick",
    "warn", "unwarn", "rmwarn", "resetwarns", "warnlimit", "warnaction",
    "info", "logs", "sangmata", "welcome", "bienvenue",
    "save", "note", "clear", "delnote", "filter", "filtre", "stop", "delfilter", "setrules", "setregles",
    "lock", "verrou", "unlock", "deverrou", "locks", "verrous",
    "purge", "del", "suppr", "pin", "epingle", "unpin", "desepingle", "feur",
    "mod", "modo", "promote", "unmod", "unmodo", "demod", "demote", "jeux", "delcitation", "uncite",
)

ALL, STAFF, ADMIN = "all", "staff", "admin"

# Clé -> (bouton, public, texte). Les /commandes sont cliquables dans Telegram.
SECTIONS = {
    "jeux": (
        "🎮 Jeux",
        ALL,
        "<b>🎮 Jeux</b>\n"
        "/flocko — ton taux de flocko, nouveau tirage toutes les 12 h\n"
        "/topflocko — le classement en image (records de tous les temps, jamais remis à zéro)\n"
        "/roulette — 1 chance sur 6 de prendre 1 minute de mute\n"
        "/duel <i>@pseudo</i> — l'autre accepte, le perdant est mute 1 minute\n"
        "/prison — qui est mute ou banni en ce moment\n"
        "/motinterdit — un mot secret par jour : celui qui le dit explose 💥\n"
        "/feurboard — les plus grosses victimes du feur",
    ),
    "fun": (
        "🎉 Fun",
        ALL,
        "<b>🎉 Fun</b>\n"
        "/blague — une blague nulle (pléonasme)\n"
        "/couple — le couple du jour · /elu — le boloss du jour\n"
        "/love <i>@a @b</i> — compatibilité amoureuse (fixe pour la journée, pas de triche)\n"
        "/qi <i>@pseudo</i> — le QI du jour\n"
        "/hack <i>@pseudo</i> — piratage (très) faux, en direct\n"
        "/clash <i>@pseudo</i> — une insulte vieille France\n"
        "/moqueur — en réponse : répète le message en mOdE mOqUeUr\n"
        "/pileouface · /de · /dard · /slot · /foot · /basket · /bowling\n"
        "/boule <i>question</i> — la boule magique, fiabilité douteuse\n"
        "/quoi — devine.\n\n"
        "<i>Et je réponds tout seul : quoi → feur, oui → stiti, non → bril, hein → deux / apagnan…</i>",
    ),
    "memoire": (
        "📜 Mémoire",
        ALL,
        "<b>📜 La mémoire du groupe</b>\n"
        "/citer — en réponse : grave le message dans le livre d'or\n"
        "/citation — une perle au hasard · <i>/citation @pseudo</i> · <i>/citation 12</i>\n"
        "/top — les bavards de la semaine (et le fantôme)\n"
        "/anniv <i>JJ/MM</i> — je te le souhaite à minuit, devant tout le monde\n"
        "/anniversaires — les prochains à fêter",
    ),
    "musique": (
        "🎵 Musique",
        ALL,
        "<b>🎵 Musique</b> — dans <b>n'importe quelle conversation</b>\n"
        "Tape <code>@feurzizibot</code> puis un titre ou un artiste, <b>sans appuyer sur Entrée</b> : "
        "les musiques de Deezer s'affichent au fur et à mesure.\n"
        "Chaque musique a sa pochette. Touche-en une : elle s'envoie avec sa pochette, "
        "puis se transforme en extrait de 30 s à écouter.\n"
        "<i>Rien tapé après @feurzizibot ? Je te montre le Top France.</i>",
    ),
    "pratique": (
        "🙋 Pratique",
        ALL,
        "<b>🙋 Pratique</b>\n"
        "/rules — les règles (lis-les, vraiment)\n"
        "/notes — les notes du groupe · <i>#nom</i> pour en afficher une\n"
        "/afk <i>[raison]</i> — t'absenter (ou écris « brb »)\n"
        "/report — en réponse : prévenir les admins (ou écris @admin)\n"
        "/warns — ton casier judiciaire\n"
        "/mods — l'équipe de modération\n"
        "/id · /ping",
    ),
    "moderation": (
        "🔨 Modération",
        STAFF,
        "<b>🔨 Modération</b> — en réponse à un message, ou avec <i>@pseudo</i> / ID\n"
        "/ban <i>[durée] [raison]</i> — bannir (sans durée = définitif)\n"
        "/deban — débannir\n"
        "/mute <i>[durée] [raison]</i> — rendre muet (sans durée = définitif)\n"
        "/demute — rendre la parole\n"
        "/kick <i>[raison]</i> — expulser (il peut revenir avec un lien)\n\n"
        "Durées : <code>30s</code> <code>10m</code> <code>1h</code> <code>1d</code>/<code>1j</code> <code>1w</code>, "
        "combinables : <code>1h30m</code>.\n"
        "Au ban / mute, ta commande et le message visé disparaissent, et un bouton « ↩️ Annuler » apparaît.\n"
        "<i>Ex : /mute @pseudo 1h a dit « quoi » sans prévenir</i>",
    ),
    "warns": (
        "⚠️ Warns",
        STAFF,
        "<b>⚠️ Warns</b> — en réponse, ou avec <i>@pseudo</i> / ID\n"
        "/warn <i>[raison]</i> — avertir (bouton « 🧽 Retirer »)\n"
        "/unwarn — retirer le dernier · /resetwarns — tout effacer\n"
        "/warns — voir les warns (tout le monde peut)\n"
        "👑 /warnlimit <i>3</i> — warns avant la sanction · 👑 /warnaction <i>mute|ban|kick</i>\n"
        "<i>À la limite, la sanction tombe toute seule (mute = 24 h) et le compteur repart à zéro.</i>",
    ),
    "outils": (
        "🔎 Infos & outils",
        STAFF,
        "<b>🔎 Infos et outils</b>\n"
        "/info <i>[@pseudo|ID]</i> — fiche : sanctions, warns, historique des pseudos\n"
        "/logs <i>[nombre]</i> — dernières sanctions\n"
        "/purge — en réponse : efface tout jusqu'à ta commande\n"
        "/del — en réponse : supprime le message\n"
        "/pin <i>[silence]</i> · /unpin — épingler / désépingler\n"
        "/delcitation <i>12</i> — retirer une citation du livre d'or",
    ),
    "notes": (
        "📝 Notes & filtres",
        ADMIN,
        "<b>📝 Notes, filtres et règles</b>\n"
        "/save <i>nom texte</i> — créer une note (ou en réponse à un message / média)\n"
        "/clear <i>nom</i> — supprimer une note\n"
        "/filter <i>mot réponse</i> — je réponds tout seul quand quelqu'un écrit le mot "
        "(<i>\"plusieurs mots\"</i> entre guillemets)\n"
        "/filters — la liste · /stop <i>mot</i> — supprimer\n"
        "/setrules <i>texte</i> — définir les règles\n"
        "Variables : <code>{mention}</code> <code>{name}</code> <code>{username}</code> <code>{id}</code> "
        "<code>{chat}</code> <code>{count}</code>",
    ),
    "bienvenue": (
        "👋 Bienvenue",
        ADMIN,
        "<b>👋 Bienvenue</b> — une variante au hasard à chaque arrivée\n"
        "/welcome — état et aperçu\n"
        "<i>/welcome list</i> — les variantes · <i>/welcome add texte</i> — en ajouter une · "
        "<i>/welcome del 3</i> — en retirer une\n"
        "<i>/welcome texte</i> — tout remplacer par un seul texte\n"
        "Photo / GIF / vidéo avec la légende <i>/welcome</i> (ou en réponse à un média) — ajoute le média\n"
        "<i>/welcome nomedia</i> · <i>/welcome on|off</i> · <i>/welcome reset</i>\n"
        "Variables : <code>{mention}</code> <code>{name}</code> <code>{username}</code> <code>{count}</code> "
        "<code>{chat}</code>",
    ),
    "verrous": (
        "🔒 Verrous",
        ADMIN,
        "<b>🔒 Verrous</b> — /lock <i>type</i> · /unlock <i>type</i> · /locks\n"
        "<code>liens</code> — je supprime les liens et pubs (PUB = MUTE, tout ça)\n"
        "<code>transferts</code> — je supprime les messages transférés\n"
        "<code>medias</code> · <code>stickers</code> · <code>sondages</code> · <code>apercus</code> — coupe ces droits\n"
        "<code>tout</code> — groupe en lecture seule\n"
        "<i>Admins et modos ne sont jamais bloqués par les suppressions.</i>",
    ),
    "modos": (
        "🛡 Modos",
        ADMIN,
        "<b>🛡 Modos</b>\n"
        "/mod <i>@pseudo|ID</i> — nommer modo (ou en réponse) · /unmod — retirer\n"
        "/mods — voir l'équipe\n\n"
        "Un modo peut : ban, mute, kick, warn, déban, démute, purge, del, pin, /info, /logs et les boutons.\n"
        "Il ne peut pas : configurer le bot, ni sanctionner un autre modo ou un admin.\n"
        "<i>Ce n'est pas un admin Telegram : avec /lock tout, il ne peut plus écrire non plus.</i>",
    ),
    "reglages": (
        "⚙️ Réglages",
        ADMIN,
        "<b>⚙️ Réglages</b> — tout se règle avec <i>on</i> / <i>off</i>\n"
        "/feur — réponses « quoi → feur », réactions 🤡 et titres du feurboard\n"
        "/jeux — roulette et duels\n"
        "/motinterdit <i>on|off</i> — le mot interdit du jour (en privé, je te le révèle)\n"
        "/sangmata — annoncer les changements de pseudo dans le groupe\n"
        "/warnlimit · /warnaction — la limite de warns",
    ),
}
MUSIC_HELP = SECTIONS["musique"][2]
AUDIENCES = {ALL: (ALL,), STAFF: (ALL, STAFF), ADMIN: (ALL, STAFF, ADMIN)}
ROLES = {ALL: "👤 membre", STAFF: "🛡 modo", ADMIN: "👑 admin du bot"}
TIPS = [
    "dis « quoi » et observe.",
    "/flocko se recharge toutes les 12 h. Le record, lui, reste à vie.",
    "réponds à une perle avec /citer pour l'immortaliser.",
    "il y a un mot interdit aujourd'hui. Je dis ça, je dis rien.",
    "/help <i>commande</i> pour l'aide d'une seule commande, ex : /help duel",
    "/anniv 12/03 et je te le souhaite devant tout le monde.",
    "/roulette n'a jamais tué personne. Enfin, 1 minute par-ci par-là.",
    "tape @feurzizibot suivi d'un titre pour chercher une musique, sans appuyer sur Entrée.",
]


async def _role(user_id: int, cfg: Config, db: Database) -> str:
    if user_id in cfg.admin_ids:
        return ADMIN
    return STAFF if await db.is_mod(user_id) else ALL


def _visible(role: str) -> list[str]:
    return [key for key, (_, audience, _) in SECTIONS.items() if audience in AUDIENCES[role]]


def _menu(name: str, role: str) -> tuple[str, InlineKeyboardMarkup]:
    count = len(_visible(role))
    text = (
        f"<b>🤖 FeurBot</b> — le bot officiel de feurchat\n"
        f"Salut {escape(name)} ! Tu es {ROLES[role]}, voilà tes {count} rubriques 👇\n\n"
        f"💡 <i>Astuce : {random.choice(TIPS)}</i>\n"
        "<i>Les commandes marchent avec <code>/</code>, <code>.</code> ou <code>!</code>, ici ou en privé.</i>"
    )
    if role != ALL:
        text += "\n<i>👑 = réservé aux admins du bot.</i>"
    buttons = [InlineKeyboardButton(text=SECTIONS[key][0], callback_data=f"help:{key}") for key in _visible(role)]
    return text, InlineKeyboardMarkup(inline_keyboard=[buttons[i : i + 2] for i in range(0, len(buttons), 2)])


def _search(command: str, role: str) -> list[str]:
    token = re.compile(rf"(?<![\w/])/{re.escape(command)}(?!\w)", re.I)
    return [
        line
        for key in _visible(role)
        for line in SECTIONS[key][2].split("\n")[1:]
        if token.search(line)
    ]


BACK = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Retour au menu", callback_data="help:menu")]])


async def send_help(message: Message, cfg: Config, db: Database) -> None:
    role = await _role(message.from_user.id, cfg, db)
    text, keyboard = _menu(message.from_user.first_name, role)
    await message.answer(text, reply_markup=keyboard)


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message, command: CommandObject, cfg: Config, db: Database) -> None:
    if command.args == "musique":
        await message.answer(MUSIC_HELP)
        return
    if message.from_user.id in cfg.admin_ids:
        await message.answer("✅ C'est bon chef, je t'enverrai les logs ici. Même ceux à 3h du mat'.")
    else:
        await message.answer(
            "🤖 Salut, moi c'est <b>FeurBot</b>, le bot de feurchat.\n"
            "Je fais régner l'ordre et les blagues nulles (surtout les blagues nulles)."
        )
    await send_help(message, cfg, db)


@router.message(Command("help", "aide", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_help(message: Message, command: CommandObject, cfg: Config, db: Database) -> None:
    wanted = (command.args or "").strip().lstrip("./!").split("@")[0].lower()
    if not wanted:
        await send_help(message, cfg, db)
        return
    lines = _search(wanted, await _role(message.from_user.id, cfg, db))
    if lines:
        await message.reply(f"🔎 <b>Aide pour /{escape(wanted)}</b>\n" + "\n".join(lines))
    else:
        await message.reply(f"🤷 Je ne connais pas /{escape(wanted)}. Tape /help pour le menu complet.")


@router.callback_query(F.data.startswith("help:"))
async def on_help(callback: CallbackQuery, cfg: Config, db: Database) -> None:
    key = callback.data.removeprefix("help:")
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    role = await _role(callback.from_user.id, cfg, db)
    if key == "menu":
        text, keyboard = _menu(callback.from_user.first_name, role)
        await callback.message.edit_text(text, reply_markup=keyboard)
    elif key in SECTIONS:
        if key not in _visible(role):
            await callback.answer("🔒 Cette rubrique est réservée à l'équipe. Joli essai.", show_alert=True)
            return
        await callback.message.edit_text(SECTIONS[key][2], reply_markup=BACK)
    await callback.answer()


@router.message(Command(*ADMIN_ONLY, prefix=PREFIXES, ignore_case=True), IsAnonymousAdmin())
async def anonymous_admin(message: Message) -> None:
    await message.reply(
        "⚠️ Tu écris en mode anonyme, je ne peux pas savoir quel admin tu es.\n"
        "Désactive « Rester anonyme » dans tes droits d'admin. Le masque, c'est pour le carnaval."
    )


@router.message(Command(*ADMIN_ONLY, prefix=PREFIXES, ignore_case=True), F.from_user)
async def not_admin(message: Message, cfg: Config, db: Database) -> None:
    if message.from_user.id in cfg.admin_ids or message.chat.id != cfg.chat_id:
        return
    if on_cooldown(f"taunt:{message.from_user.id}", 60):
        return
    if await db.is_mod(message.from_user.id):
        await message.reply("🔒 Ça, c'est réservé aux admins du bot. T'es modo, c'est déjà pas mal 😌")
    else:
        await message.reply(quip("not_admin"))
