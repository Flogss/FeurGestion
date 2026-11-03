"""Aide à boutons, /start, et répliques quand un non-admin joue au chef."""

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ..config import Config
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
)

MENU = (
    "<b>🤖 FeurBot — panneau de contrôle</b>\n"
    "Le bot officiel de feurchat : de l'ordre, des logs, et des blagues nulles.\n"
    "Choisis une catégorie 👇\n\n"
    "<i>Préfixes : <code>.</code> <code>!</code> <code>/</code> — ça marche aussi en privé avec moi.</i>"
)

SECTIONS = {
    "moderation": (
        "🔨 Modération",
        "<b>🔨 Modération</b> — en réponse à un message, ou avec <code>@pseudo</code> / ID\n"
        "<code>.ban [durée] [raison]</code> — bannir (sans durée = définitif)\n"
        "<code>.deban</code> — débannir\n"
        "<code>.mute [durée] [raison]</code> — rendre muet (sans durée = définitif)\n"
        "<code>.demute</code> — rendre la parole\n"
        "<code>.kick [raison]</code> — expulser (il peut revenir avec un lien)\n\n"
        "Durées : <code>30s</code> <code>10m</code> <code>1h</code> <code>1d</code>/<code>1j</code> <code>1w</code>, "
        "combinables : <code>1h30m</code>. Raison et durée facultatives.\n"
        "Au ban / mute, ta commande et le message visé disparaissent, et un bouton « ↩️ Annuler » apparaît.\n"
        "<i>Ex : <code>.mute @pseudo 1h a dit « quoi » sans prévenir</code></i>",
    ),
    "warns": (
        "⚠️ Warns",
        "<b>⚠️ Warns</b> — en réponse, ou avec <code>@pseudo</code> / ID\n"
        "<code>.warn [raison]</code> — avertir (bouton « 🧽 Retirer »)\n"
        "<code>.unwarn</code> — retirer le dernier warn\n"
        "<code>.resetwarns</code> — tout effacer\n"
        "<code>.warns</code> — voir les warns (tout le monde peut)\n"
        "<code>.warnlimit 3</code> — nombre de warns avant la sanction\n"
        "<code>.warnaction mute|ban|kick</code> — la sanction (mute = 24h)\n"
        "<i>À la limite, la sanction tombe toute seule et le compteur repart à zéro.</i>",
    ),
    "notes": (
        "📝 Notes & filtres",
        "<b>📝 Notes, filtres et règles</b>\n"
        "<code>.save nom texte</code> — créer une note (ou en réponse à un message / média)\n"
        "<code>#nom</code> ou <code>.get nom</code> — l'afficher (tout le monde)\n"
        "<code>.notes</code> — la liste · <code>.clear nom</code> — supprimer\n\n"
        "<code>.filter mot réponse</code> — je réponds tout seul quand quelqu'un écrit le mot "
        "(<code>\"plusieurs mots\"</code> entre guillemets)\n"
        "<code>.filters</code> — la liste · <code>.stop mot</code> — supprimer\n\n"
        "<code>.setrules texte</code> — définir les règles · <code>.rules</code> — les afficher\n"
        "Variables : <code>{mention}</code> <code>{name}</code> <code>{username}</code> <code>{id}</code> "
        "<code>{chat}</code> <code>{count}</code>",
    ),
    "verrous": (
        "🔒 Verrous",
        "<b>🔒 Verrous</b> — <code>.lock type</code> / <code>.unlock type</code> / <code>.locks</code>\n"
        "<code>liens</code> — je supprime les liens et pubs des non-admins (PUB = MUTE, tout ça)\n"
        "<code>transferts</code> — je supprime les messages transférés\n"
        "<code>medias</code> · <code>stickers</code> · <code>sondages</code> · <code>apercus</code> — coupe ces droits\n"
        "<code>tout</code> — groupe en lecture seule (pratique la nuit)\n"
        "<i>Les admins ne sont jamais bloqués. Privilège de l'âge.</i>",
    ),
    "bienvenue": (
        "👋 Bienvenue",
        "<b>👋 Bienvenue</b>\n"
        "<code>.welcome</code> — voir le message actuel\n"
        "<code>.welcome texte</code> — changer le texte (garde le média)\n"
        "Photo / GIF / vidéo avec la légende <code>.welcome texte</code>, ou en réponse à un média\n"
        "<code>.welcome nomedia</code> — retirer le média\n"
        "<code>.welcome on</code> / <code>off</code> · <code>.welcome reset</code>\n"
        "Variables : <code>{mention}</code> <code>{name}</code> <code>{username}</code> <code>{id}</code> "
        "<code>{chat}</code> <code>{count}</code>",
    ),
    "infos": (
        "🔎 Infos & outils",
        "<b>🔎 Infos et outils</b>\n"
        "<code>.info [@pseudo|ID]</code> — fiche : sanctions, warns, historique des pseudos\n"
        "<code>.logs [nombre]</code> — dernières sanctions\n"
        "<code>.sangmata on|off</code> — annoncer dans le groupe quand quelqu'un change de pseudo\n"
        "<code>.purge</code> — en réponse : efface tout jusqu'à ta commande\n"
        "<code>.del</code> — supprime le message visé\n"
        "<code>.pin [silence]</code> / <code>.unpin</code> — épingler / désépingler\n"
        "<code>.id</code> · <code>.ping</code> · <code>.report</code> — pour tout le monde",
    ),
    "fun": (
        "🎉 Fun",
        "<b>🎉 Fun</b>\n"
        "<code>.feur on|off</code> — réponses auto : quoi → feur, oui → stiti, non → bril, hein → deux…\n"
        "<code>.blague</code> — une blague nulle (pléonasme)\n"
        "<code>.pileouface</code> · <code>.de</code> · <code>.dard</code> · <code>.slot</code> · "
        "<code>.foot</code> · <code>.basket</code> · <code>.bowling</code>\n"
        "<code>.boule question</code> — la boule magique, fiabilité douteuse\n"
        "<code>.quoi</code> — devine.",
    ),
}

MEMBER_HELP = (
    "<b>🤖 FeurBot — le bot officiel de feurchat</b>\n"
    "Ce que tu peux faire (le reste, c'est pour les admins 😌) :\n\n"
    "<code>.rules</code> — les règles (lis-les, vraiment)\n"
    "<code>.notes</code> · <code>#nom</code> — les notes du groupe\n"
    "<code>.afk [raison]</code> — t'absenter (ou écris « brb »)\n"
    "<code>.report</code> — en réponse à un message : prévenir les admins\n"
    "<code>.warns</code> — ton casier judiciaire\n"
    "<code>.id</code> · <code>.ping</code>\n"
    "<code>.blague</code> · <code>.pileouface</code> · <code>.de</code> · <code>.dard</code> · <code>.slot</code> · "
    "<code>.foot</code> · <code>.basket</code> · <code>.bowling</code> · <code>.boule question</code>\n\n"
    "Et dis « quoi » pour voir. 😏"
)


def _menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=title, callback_data=f"help:{key}") for key, (title, _) in SECTIONS.items()]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i : i + 2] for i in range(0, len(buttons), 2)])


BACK = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Retour", callback_data="help:menu")]])


async def send_help(message: Message, cfg: Config) -> None:
    if message.from_user.id in cfg.admin_ids:
        await message.answer(MENU, reply_markup=_menu_keyboard())
    else:
        await message.answer(MEMBER_HELP)


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message, cfg: Config) -> None:
    if message.from_user.id in cfg.admin_ids:
        await message.answer("✅ C'est bon chef, je t'enverrai les logs ici. Même ceux à 3h du mat'.")
    else:
        await message.answer(
            "🤖 Salut, moi c'est <b>FeurBot</b>, le bot de feurchat.\n"
            "Je fais régner l'ordre et les blagues nulles (surtout les blagues nulles)."
        )
    await send_help(message, cfg)


@router.message(Command("help", "aide", prefix=PREFIXES, ignore_case=True), IsMember())
async def cmd_help(message: Message, cfg: Config) -> None:
    await send_help(message, cfg)


@router.callback_query(F.data.startswith("help:"))
async def on_help(callback: CallbackQuery) -> None:
    key = callback.data.removeprefix("help:")
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    if key == "menu":
        await callback.message.edit_text(MENU, reply_markup=_menu_keyboard())
    elif key in SECTIONS:
        await callback.message.edit_text(SECTIONS[key][1], reply_markup=BACK)
    await callback.answer()


@router.message(Command(*ADMIN_ONLY, prefix=PREFIXES, ignore_case=True), IsAnonymousAdmin())
async def anonymous_admin(message: Message) -> None:
    await message.reply(
        "⚠️ Tu écris en mode anonyme, je ne peux pas savoir quel admin tu es.\n"
        "Désactive « Rester anonyme » dans tes droits d'admin. Le masque, c'est pour le carnaval."
    )


@router.message(Command(*ADMIN_ONLY, prefix=PREFIXES, ignore_case=True), F.from_user)
async def not_admin(message: Message, cfg: Config) -> None:
    if message.from_user.id in cfg.admin_ids or message.chat.id != cfg.chat_id:
        return
    if not on_cooldown(f"taunt:{message.from_user.id}", 60):
        await message.reply(quip("not_admin"))
