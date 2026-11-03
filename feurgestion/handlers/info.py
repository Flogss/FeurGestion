from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from ..config import Config
from ..db import Database, full_name
from ..filters import IsAdmin, IsAnonymousAdmin
from ..targets import Target, resolve_target
from ..utils import (
    ACTION_LABELS,
    PREFIXES,
    chunk_lines,
    format_date,
    format_duration,
    mention,
    shorten,
)

router = Router(name="info")

ALL_COMMANDS = ("ban", "unban", "deban", "mute", "unmute", "demute", "kick", "info", "logs", "help", "aide", "welcome")

HELP = """<b>🤖 FeurGestion — commandes</b>

<b>Modération</b> — en réponse à un message, ou avec <code>@pseudo</code> / ID
<code>.ban [durée] [raison]</code> — bannir (sans durée = définitif)
<code>.deban</code> — débannir (ou <code>.unban</code>)
<code>.mute [durée] [raison]</code> — rendre muet (sans durée = définitif)
<code>.demute</code> — rendre la parole (ou <code>.unmute</code>)
<code>.kick [raison]</code> — expulser (peut revenir avec un lien)
Raison et durée sont facultatives. Au <code>.mute</code>, ta commande et le message visé sont supprimés.
Bouton « ↩️ Annuler » sous chaque ban / mute.
Durées : <code>30s</code> <code>10m</code> <code>1h</code> <code>1d</code>/<code>1j</code> <code>1w</code>, combinables : <code>1h30m</code>
Ex : <code>.mute @pseudo 1h spam</code> · <code>.ban 123456789 pub</code>

<b>Infos &amp; logs</b>
<code>.info [@pseudo|ID]</code> — fiche complète + historique
<code>.logs [nombre]</code> — dernières sanctions

<b>Bienvenue</b>
<code>.welcome</code> — voir le message actuel
<code>.welcome texte</code> — changer le texte (garde le média)
Photo / GIF / vidéo avec la légende <code>.welcome texte</code> (ou en réponse à un média) — avec média
<code>.welcome nomedia</code> — retirer le média
<code>.welcome on</code> / <code>.welcome off</code> — activer / désactiver
<code>.welcome reset</code> — message par défaut
Variables : <code>{mention}</code> <code>{name}</code> <code>{username}</code> <code>{id}</code> <code>{chat}</code> <code>{count}</code>

Les commandes marchent aussi en privé avec moi."""


def describe_status(member, cfg: Config) -> str:
    status = member.status
    if status == ChatMemberStatus.CREATOR:
        return "👑 Créateur"
    if status == ChatMemberStatus.ADMINISTRATOR:
        return "🛡 Admin"
    if status == ChatMemberStatus.MEMBER:
        return "✅ Membre"
    if status == ChatMemberStatus.LEFT:
        return "🚪 Pas dans le groupe"

    until = member.until_date
    end = " définitivement" if until is None or until.timestamp() <= 0 else f" jusqu'au {format_date(until, cfg)}"
    if status == ChatMemberStatus.KICKED:
        return f"🔨 Banni{end}"
    text = ("🔇 Mute" if not member.can_send_messages else "⚠️ Restreint") + end
    if not member.is_member:
        text += " (pas dans le groupe)"
    return text


async def _admin_names(db: Database, rows) -> dict[int, str]:
    names = {}
    for admin_id in {row["admin_id"] for row in rows if row["admin_id"]}:
        user = await db.get_user(admin_id)
        names[admin_id] = full_name(user["first_name"], user["last_name"]) if user else str(admin_id)
    return names


def _entry(row, cfg: Config, admins: dict[int, str]) -> list[str]:
    parts = [format_date(row["created_at"], cfg), ACTION_LABELS.get(row["action"], row["action"])]
    if row["action"] in ("ban", "mute"):
        parts.append(format_duration(row["duration"]))
    if row["reason"]:
        parts.append(escape(shorten(row["reason"])))
    by = row["admin_id"]
    if by and by != row["user_id"]:
        parts.append(f"par {escape(admins.get(by, str(by)))}")
    return parts


def _periods(names, key: str) -> list[list]:
    """Regroupe l'historique en périodes [valeur, début, fin] (fin = None : valeur actuelle)."""
    periods = []
    for row in names:
        if periods and periods[-1][0] == row[key]:
            continue
        if periods:
            periods[-1][2] = row["seen_at"]
        periods.append([row[key], row["seen_at"], None])
    return periods


def _period_lines(periods, render, cfg: Config) -> list[str]:
    lines = []
    for value, start, end in reversed(periods):
        when = (
            f"actuel, vu depuis le {format_date(start, cfg)}"
            if end is None
            else f"du {format_date(start, cfg)} au {format_date(end, cfg)}"
        )
        lines.append(f"• {render(value)} — {when}")
    return lines


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message, cfg: Config) -> None:
    if message.from_user.id in cfg.admin_ids:
        await message.answer("✅ C'est bon, je t'enverrai les logs ici.\n\n" + HELP)
    else:
        await message.answer("🤖 Je suis le bot de gestion de feurchat.")


@router.message(Command("help", "aide", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_help(message: Message) -> None:
    await message.reply(HELP)


@router.message(Command("info", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_info(message: Message, command: CommandObject, bot: Bot, db: Database, cfg: Config) -> None:
    target, _, error = await resolve_target(message, command.args or "", bot, db, cfg)
    if error:
        await message.reply(error)
        return
    if target is None:
        target = Target.from_user(message.from_user)

    status = "❔ Inconnu (jamais vu dans le groupe)"
    is_bot = False
    try:
        member = await bot.get_chat_member(cfg.chat_id, target.id)
        target = Target.from_user(member.user)
        is_bot = member.user.is_bot
        status = describe_status(member, cfg)
        await db.track_user(member.user, active=False)
    except TelegramAPIError:
        pass

    row = await db.get_user(target.id)
    counts = await db.action_counts(target.id)
    history = await db.user_actions(target.id, 10)
    names = await db.name_history(target.id)
    last_join = await db.last_action(target.id, "join")
    admins = await _admin_names(db, history)

    lines = [
        "<b>👤 Fiche utilisateur</b>",
        f"Nom : {target.mention}",
        f"Pseudo : {'@' + escape(target.username) if target.username else 'aucun'}",
        f"ID : <code>{target.id}</code>",
    ]
    if is_bot:
        lines.append("🤖 C'est un bot")
    lines += [
        f"Statut : {status}",
        "",
        "<b>📊 Activité</b> <i>(depuis mon arrivée)</i>",
        f"Vu la 1re fois : {format_date(row['first_seen'], cfg) if row else '—'}",
        f"Dernier message : {format_date(row['last_seen'], cfg) if row else '—'}",
        f"Messages : {row['message_count'] if row else 0}",
        f"Dernière arrivée : {format_date(last_join['created_at'], cfg) if last_join else '—'}",
        "",
        "<b>⚖️ Sanctions</b>",
        f"🔨 Bans : {counts.get('ban', 0)} · 🔇 Mutes : {counts.get('mute', 0)} · 👢 Kicks : {counts.get('kick', 0)}",
    ]
    if history:
        lines += ["", "<b>🕓 Historique</b> <i>(10 derniers)</i>"]
        lines += ["• " + " — ".join(_entry(entry, cfg, admins)) for entry in history]
    if names:
        lines += ["", "<b>📝 Historique des pseudos</b> <i>(depuis mon arrivée)</i>"]
        lines += _period_lines(
            _periods(names, "username"), lambda u: f"@{escape(u)}" if u else "<i>sans pseudo</i>", cfg
        )
        name_periods = _periods(names, "full_name")
        if len(name_periods) > 1:
            lines += ["", "<b>📛 Historique des noms</b>"]
            lines += _period_lines(name_periods, escape, cfg)

    for chunk in chunk_lines(lines):
        await message.reply(chunk)


@router.message(Command("logs", prefix=PREFIXES, ignore_case=True), IsAdmin())
async def cmd_logs(message: Message, command: CommandObject, db: Database, cfg: Config) -> None:
    arg = (command.args or "").strip()
    limit = max(1, min(int(arg), 100)) if arg.isdigit() else 15
    rows = await db.recent_sanctions(limit)
    if not rows:
        await message.reply("📭 Aucune sanction enregistrée pour l'instant.")
        return

    admins = await _admin_names(db, rows)
    lines = [f"<b>📜 {len(rows)} dernières sanctions</b>"]
    for row in rows:
        who = mention(row["user_id"], full_name(row["first_name"], row["last_name"]) if row["first_name"] else str(row["user_id"]))
        entry = _entry(row, cfg, admins)
        entry.insert(2, f"{who} (<code>{row['user_id']}</code>)")
        lines.append("• " + " — ".join(entry))

    for chunk in chunk_lines(lines):
        await message.reply(chunk)


@router.message(Command(*ALL_COMMANDS, prefix=PREFIXES, ignore_case=True), IsAnonymousAdmin())
async def anonymous_admin(message: Message) -> None:
    await message.reply(
        "⚠️ Tu écris en mode anonyme, je ne peux pas savoir quel admin tu es.\n"
        "Désactive « Rester anonyme » dans tes droits d'admin pour utiliser mes commandes."
    )
