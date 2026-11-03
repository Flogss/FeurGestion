from aiogram import Dispatcher

from .config import Config
from .db import Database
from .handlers import afk, events, fun, help, info, locks, moderation, notes, passive, tools, warns, welcome
from .middlewares import GuardMiddleware, TrackerMiddleware


def build_dispatcher(cfg: Config, db: Database) -> Dispatcher:
    dp = Dispatcher(cfg=cfg, db=db)
    dp.message.outer_middleware(TrackerMiddleware(db, cfg))
    dp.message.outer_middleware(GuardMiddleware(db, cfg))
    # L'ordre compte : commandes d'abord, répliques aux non-admins ensuite, messages ordinaires en dernier
    dp.include_routers(
        moderation.router,
        warns.router,
        notes.router,
        locks.router,
        tools.router,
        afk.router,
        fun.router,
        welcome.router,
        info.router,
        help.router,
        events.router,
        passive.router,
    )
    return dp
