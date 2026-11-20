"""Le menu « / » de Telegram : chacun voit les commandes de son rôle quand il tape /."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeChat,
    BotCommandScopeChatMember,
    BotCommandScopeDefault,
)

from .config import Config
from .db import Database

log = logging.getLogger(__name__)

PUBLIC = [
    ("help", "Le menu d'aide (avec des boutons, la classe)"),
    ("flocko", "Ton taux de flocko, nouveau toutes les 12 h"),
    ("topflocko", "Le classement flocko en image"),
    ("roulette", "1 chance sur 6 d'être mute 1 minute"),
    ("duel", "Défier quelqu'un : le perdant est mute 1 min"),
    ("prison", "Qui est mute ou banni en ce moment"),
    ("motinterdit", "Le mot interdit du jour (ne le dis pas)"),
    ("feurboard", "Les plus grosses victimes du feur"),
    ("blague", "Une blague nulle"),
    ("couple", "Le couple du jour"),
    ("elu", "Le boloss du jour"),
    ("love", "Compatibilité amoureuse (@a @b)"),
    ("qi", "Le QI du jour de quelqu'un"),
    ("hack", "Pirater quelqu'un (pour de faux)"),
    ("clash", "Une insulte vieille France"),
    ("moqueur", "En réponse : répéter en mOdE mOqUeUr"),
    ("citer", "En réponse : graver un message dans le livre d'or"),
    ("citation", "Une citation au hasard du livre d'or"),
    ("top", "Le top des bavards de la semaine"),
    ("anniv", "Enregistrer ton anniversaire (JJ/MM)"),
    ("anniversaires", "Les prochains anniversaires"),
    ("pileouface", "Pile ou face"),
    ("de", "Lancer un dé"),
    ("boule", "La boule magique répond à ta question"),
    ("rules", "Les règles du groupe"),
    ("notes", "Les notes du groupe"),
    ("afk", "Partir AFK (le bot prévient les autres)"),
    ("report", "En réponse : signaler un message aux admins"),
    ("warns", "Voir les warns de quelqu'un"),
    ("mods", "L'équipe de modération"),
    ("id", "Afficher les IDs"),
    ("ping", "Le bot est-il vivant ?"),
]
STAFF = [
    ("ban", "Bannir [durée] [raison]"),
    ("mute", "Rendre muet [durée] [raison]"),
    ("kick", "Expulser [raison]"),
    ("deban", "Débannir"),
    ("demute", "Rendre la parole"),
    ("warn", "Avertir [raison]"),
    ("unwarn", "Retirer le dernier warn"),
    ("resetwarns", "Effacer tous les warns"),
    ("purge", "En réponse : tout effacer jusqu'ici"),
    ("del", "En réponse : supprimer le message"),
    ("pin", "En réponse : épingler"),
    ("unpin", "Désépingler"),
    ("info", "Fiche complète de quelqu'un"),
    ("logs", "Dernières sanctions"),
    ("delcitation", "Supprimer une citation (numéro)"),
]
ADMIN = [
    ("mod", "Nommer quelqu'un modo"),
    ("unmod", "Retirer le rôle de modo"),
    ("welcome", "Régler le message de bienvenue"),
    ("lock", "Verrouiller (liens, médias…)"),
    ("unlock", "Déverrouiller"),
    ("locks", "État des verrous"),
    ("antiflood", "Anti-flood : doux, normal, strict ou off"),
    ("save", "Créer une note"),
    ("clear", "Supprimer une note"),
    ("filter", "Créer une réponse automatique"),
    ("stop", "Supprimer une réponse automatique"),
    ("setrules", "Définir les règles"),
    ("feur", "Réponses « quoi → feur » on/off"),
    ("jeux", "Roulette et duels on/off"),
    ("sangmata", "Annonces de changement de pseudo on/off"),
    ("warnlimit", "Nombre de warns avant sanction"),
    ("warnaction", "Sanction à la limite de warns"),
    ("backup", "Sauvegarde de la base (en privé)"),
]


def _commands(*groups) -> list[BotCommand]:
    return [BotCommand(command=name, description=text) for group in groups for name, text in group]


async def _set(bot: Bot, commands: list[BotCommand], scope) -> None:
    try:
        await bot.set_my_commands(commands, scope=scope)
    except TelegramAPIError as exc:
        log.warning("Menu de commandes non mis à jour (%s) : %s", type(scope).__name__, exc)


async def set_mod_commands(bot: Bot, cfg: Config, user_id: int, is_mod: bool) -> None:
    scope = BotCommandScopeChatMember(chat_id=cfg.chat_id, user_id=user_id)
    if is_mod:
        await _set(bot, _commands(PUBLIC, STAFF), scope)
        return
    try:
        await bot.delete_my_commands(scope=scope)
    except TelegramAPIError as exc:
        log.warning("Menu de commandes du modo %s non retiré : %s", user_id, exc)


async def sync_commands(bot: Bot, cfg: Config, db: Database) -> None:
    """Au démarrage : menu public pour tous, menu complet pour les admins, menu staff pour les modos."""
    await _set(bot, _commands(PUBLIC), BotCommandScopeDefault())
    await _set(bot, _commands(PUBLIC), BotCommandScopeAllGroupChats())
    everything = _commands(PUBLIC, STAFF, ADMIN)
    for admin_id in cfg.admin_ids:
        await _set(bot, everything, BotCommandScopeChatMember(chat_id=cfg.chat_id, user_id=admin_id))
        await _set(bot, everything, BotCommandScopeChat(chat_id=admin_id))
    for row in await db.list_mods():
        await set_mod_commands(bot, cfg, row["user_id"], True)
