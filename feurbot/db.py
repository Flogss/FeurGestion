import json
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiosqlite
from aiogram.types import User

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    first_name    TEXT,
    last_name     TEXT,
    is_bot        INTEGER NOT NULL DEFAULT 0,
    first_seen    INTEGER NOT NULL,
    last_seen     INTEGER,
    message_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username COLLATE NOCASE);

-- Chaque pseudo / nom différent vu pour un utilisateur
CREATE TABLE IF NOT EXISTS name_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    username  TEXT,
    full_name TEXT,
    seen_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_names_user ON name_history(user_id, seen_at);

-- Journal : sanctions (ban, unban, mute, unmute, kick) et mouvements (join, leave)
CREATE TABLE IF NOT EXISTS actions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    action     TEXT NOT NULL,
    user_id    INTEGER NOT NULL,
    admin_id   INTEGER,
    reason     TEXT,
    duration   INTEGER,
    until      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_actions_user ON actions(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_actions_time ON actions(created_at);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS warns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    admin_id   INTEGER,
    reason     TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_warns_user ON warns(user_id);

-- Notes (#nom) et filtres (réponses automatiques), même format
CREATE TABLE IF NOT EXISTS snippets (
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL COLLATE NOCASE,
    text       TEXT,
    media_type TEXT,
    file_id    TEXT,
    created_by INTEGER,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (kind, name)
);

-- Nombre de « quoi » dits par personne (le feurboard)
CREATE TABLE IF NOT EXISTS feur_stats (
    user_id INTEGER PRIMARY KEY,
    count   INTEGER NOT NULL DEFAULT 0
);

-- Messages par personne et par jour (pour .top)
CREATE TABLE IF NOT EXISTS activity (
    user_id INTEGER NOT NULL,
    day     TEXT NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

-- Le livre d'or (.citer / .citation)
CREATE TABLE IF NOT EXISTS quotes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    text        TEXT NOT NULL,
    said_at     INTEGER NOT NULL,
    message_id  INTEGER UNIQUE,
    saved_by    INTEGER
);

CREATE TABLE IF NOT EXISTS birthdays (
    user_id INTEGER PRIMARY KEY,
    day     INTEGER NOT NULL,
    month   INTEGER NOT NULL
);

-- /flocko : dernier tirage et meilleur score de chacun (le classement ne se remet jamais à zéro)
CREATE TABLE IF NOT EXISTS flocko (
    user_id INTEGER PRIMARY KEY,
    last    INTEGER NOT NULL,
    last_at INTEGER NOT NULL,
    best    INTEGER NOT NULL,
    best_at INTEGER NOT NULL,
    rolls   INTEGER NOT NULL DEFAULT 0
);

-- Modérateurs nommés avec .mod : ils peuvent sanctionner, pas configurer le bot
CREATE TABLE IF NOT EXISTS mods (
    user_id  INTEGER PRIMARY KEY,
    added_by INTEGER,
    added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS afk (
    user_id INTEGER PRIMARY KEY,
    reason  TEXT,
    since   INTEGER NOT NULL
);
"""

SANCTIONS = ("ban", "unban", "mute", "unmute", "kick")


def full_name(first: str | None, last: str | None) -> str:
    return " ".join(part for part in (first, last) if part) or "Sans nom"


class Database:
    def __init__(self, path: str, tz: ZoneInfo | None = None) -> None:
        self.path = path
        self.tz = tz or ZoneInfo("UTC")
        self.conn: aiosqlite.Connection | None = None

    def today(self, offset_days: int = 0) -> str:
        """Date du jour (fuseau du groupe) au format AAAA-MM-JJ."""
        return (datetime.now(self.tz) + timedelta(days=offset_days)).strftime("%Y-%m-%d")

    async def connect(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    # --- Utilisateurs ---

    async def track_user(self, user: User, active: bool) -> tuple[str | None, str] | None:
        """Enregistre un utilisateur vu. `active` = il vient d'envoyer un message.

        Retourne (ancien pseudo, ancien nom) si une personne déjà connue a changé de pseudo ou de nom.
        """
        now = int(time.time())
        username = user.username
        name = full_name(user.first_name, user.last_name)

        existing = await self.get_user(user.id)
        change = None
        if existing is not None:
            old_name = full_name(existing["first_name"], existing["last_name"])
            if existing["username"] != username or old_name != name:
                change = (existing["username"], old_name)
        if existing is None or change:
            await self.conn.execute(
                "INSERT INTO name_history(user_id, username, full_name, seen_at) VALUES (?, ?, ?, ?)",
                (user.id, username, name, now),
            )

        if username:
            # Un pseudo ne peut appartenir qu'à une personne : on libère l'ancien propriétaire
            await self.conn.execute(
                "UPDATE users SET username = NULL WHERE username = ? COLLATE NOCASE AND user_id != ?",
                (username, user.id),
            )

        await self.conn.execute(
            """
            INSERT INTO users(user_id, username, first_name, last_name, is_bot, first_seen, last_seen, message_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_seen = COALESCE(excluded.last_seen, users.last_seen),
                message_count = users.message_count + excluded.message_count
            """,
            (
                user.id,
                username,
                user.first_name,
                user.last_name,
                int(user.is_bot),
                now,
                now if active else None,
                1 if active else 0,
            ),
        )
        if active:
            await self.conn.execute(
                """
                INSERT INTO activity(user_id, day, count) VALUES (?, ?, 1)
                ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1
                """,
                (user.id, self.today()),
            )
        await self.conn.commit()
        return change

    async def get_user(self, user_id: int) -> aiosqlite.Row | None:
        async with self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone()

    async def find_by_username(self, username: str) -> aiosqlite.Row | None:
        async with self.conn.execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE ORDER BY last_seen DESC LIMIT 1",
            (username.lstrip("@"),),
        ) as cur:
            row = await cur.fetchone()
        if row:
            return row
        # Pseudo plus porté actuellement : on regarde l'historique
        async with self.conn.execute(
            """
            SELECT u.* FROM name_history h JOIN users u ON u.user_id = h.user_id
            WHERE h.username = ? COLLATE NOCASE ORDER BY h.seen_at DESC LIMIT 1
            """,
            (username.lstrip("@"),),
        ) as cur:
            return await cur.fetchone()

    async def name_history(self, user_id: int, limit: int = 50) -> list[aiosqlite.Row]:
        """Les `limit` derniers changements de nom / pseudo, du plus ancien au plus récent."""
        async with self.conn.execute(
            "SELECT * FROM name_history WHERE user_id = ? ORDER BY seen_at DESC, id DESC LIMIT ?",
            (user_id, limit),
        ) as cur:
            return list(reversed(await cur.fetchall()))

    # --- Journal ---

    async def add_action(
        self,
        action: str,
        user_id: int,
        admin_id: int | None = None,
        reason: str | None = None,
        duration: int | None = None,
        until: int | None = None,
    ) -> int:
        cur = await self.conn.execute(
            """
            INSERT INTO actions(created_at, action, user_id, admin_id, reason, duration, until)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (int(time.time()), action, user_id, admin_id, reason, duration, until),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_action(self, action_id: int) -> aiosqlite.Row | None:
        async with self.conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)) as cur:
            return await cur.fetchone()

    async def user_actions(self, user_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM actions WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (user_id, limit),
        ) as cur:
            return list(await cur.fetchall())

    async def action_counts(self, user_id: int) -> dict[str, int]:
        async with self.conn.execute(
            "SELECT action, COUNT(*) AS n FROM actions WHERE user_id = ? GROUP BY action",
            (user_id,),
        ) as cur:
            return {row["action"]: row["n"] for row in await cur.fetchall()}

    async def last_action(self, user_id: int, action: str) -> aiosqlite.Row | None:
        async with self.conn.execute(
            "SELECT * FROM actions WHERE user_id = ? AND action = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (user_id, action),
        ) as cur:
            return await cur.fetchone()

    async def recent_sanctions(self, limit: int) -> list[aiosqlite.Row]:
        placeholders = ",".join("?" * len(SANCTIONS))
        async with self.conn.execute(
            f"""
            SELECT a.*, u.username, u.first_name, u.last_name
            FROM actions a LEFT JOIN users u ON u.user_id = a.user_id
            WHERE a.action IN ({placeholders})
            ORDER BY a.created_at DESC, a.id DESC LIMIT ?
            """,
            (*SANCTIONS, limit),
        ) as cur:
            return list(await cur.fetchall())

    # --- Réglages ---

    async def get_setting(self, key: str, default=None):
        async with self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
        return json.loads(row["value"]) if row else default

    async def set_setting(self, key: str, value) -> None:
        await self.conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        await self.conn.commit()

    # --- Warns ---

    async def add_warn(self, user_id: int, admin_id: int | None, reason: str | None) -> int:
        cur = await self.conn.execute(
            "INSERT INTO warns(user_id, admin_id, reason, created_at) VALUES (?, ?, ?, ?)",
            (user_id, admin_id, reason, int(time.time())),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_warn(self, warn_id: int) -> aiosqlite.Row | None:
        async with self.conn.execute("SELECT * FROM warns WHERE id = ?", (warn_id,)) as cur:
            return await cur.fetchone()

    async def user_warns(self, user_id: int) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM warns WHERE user_id = ? ORDER BY created_at, id", (user_id,)
        ) as cur:
            return list(await cur.fetchall())

    async def remove_warn(self, warn_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM warns WHERE id = ?", (warn_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    async def clear_warns(self, user_id: int) -> int:
        cur = await self.conn.execute("DELETE FROM warns WHERE user_id = ?", (user_id,))
        await self.conn.commit()
        return cur.rowcount

    # --- Notes et filtres ---

    async def save_snippet(
        self, kind: str, name: str, text: str | None, media_type: str | None, file_id: str | None, author: int
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO snippets(kind, name, text, media_type, file_id, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, name) DO UPDATE SET
                text = excluded.text, media_type = excluded.media_type, file_id = excluded.file_id,
                created_by = excluded.created_by, created_at = excluded.created_at
            """,
            (kind, name.lower(), text, media_type, file_id, author, int(time.time())),
        )
        await self.conn.commit()

    async def get_snippet(self, kind: str, name: str) -> aiosqlite.Row | None:
        async with self.conn.execute(
            "SELECT * FROM snippets WHERE kind = ? AND name = ?", (kind, name.lower())
        ) as cur:
            return await cur.fetchone()

    async def list_snippets(self, kind: str) -> list[aiosqlite.Row]:
        async with self.conn.execute("SELECT * FROM snippets WHERE kind = ? ORDER BY name", (kind,)) as cur:
            return list(await cur.fetchall())

    async def delete_snippet(self, kind: str, name: str) -> bool:
        cur = await self.conn.execute("DELETE FROM snippets WHERE kind = ? AND name = ?", (kind, name.lower()))
        await self.conn.commit()
        return cur.rowcount > 0

    # --- AFK ---

    async def set_afk(self, user_id: int, reason: str | None) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO afk(user_id, reason, since) VALUES (?, ?, ?)",
            (user_id, reason, int(time.time())),
        )
        await self.conn.commit()

    async def get_afk(self, user_id: int) -> aiosqlite.Row | None:
        async with self.conn.execute("SELECT * FROM afk WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone()

    async def clear_afk(self, user_id: int) -> aiosqlite.Row | None:
        row = await self.get_afk(user_id)
        if row:
            await self.conn.execute("DELETE FROM afk WHERE user_id = ?", (user_id,))
            await self.conn.commit()
        return row

    # --- Modos ---

    async def add_mod(self, user_id: int, added_by: int) -> bool:
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO mods(user_id, added_by, added_at) VALUES (?, ?, ?)",
            (user_id, added_by, int(time.time())),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def remove_mod(self, user_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM mods WHERE user_id = ?", (user_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    async def is_mod(self, user_id: int) -> bool:
        async with self.conn.execute("SELECT 1 FROM mods WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone() is not None

    async def list_mods(self) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            """
            SELECT m.*, u.username, u.first_name, u.last_name
            FROM mods m LEFT JOIN users u ON u.user_id = m.user_id
            ORDER BY m.added_at
            """
        ) as cur:
            return list(await cur.fetchall())

    async def active_users(self, days: int = 7) -> list[int]:
        """Humains qui ont écrit dans les `days` derniers jours."""
        since = int(time.time()) - days * 86400
        async with self.conn.execute(
            "SELECT user_id FROM users WHERE last_seen >= ? AND is_bot = 0 ORDER BY user_id", (since,)
        ) as cur:
            return [row["user_id"] for row in await cur.fetchall()]

    # --- Feurboard ---

    async def add_feur(self, user_id: int) -> int:
        await self.conn.execute(
            """
            INSERT INTO feur_stats(user_id, count) VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET count = count + 1
            """,
            (user_id,),
        )
        await self.conn.commit()
        return await self.feur_count(user_id)

    async def feur_count(self, user_id: int) -> int:
        async with self.conn.execute("SELECT count FROM feur_stats WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        return row["count"] if row else 0

    async def feur_board(self, limit: int = 10) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            """
            SELECT f.user_id, f.count, u.first_name, u.last_name
            FROM feur_stats f LEFT JOIN users u ON u.user_id = f.user_id
            ORDER BY f.count DESC LIMIT ?
            """,
            (limit,),
        ) as cur:
            return list(await cur.fetchall())

    # --- Activité (.top) ---

    async def top_talkers(self, days: int = 7, limit: int = 10) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            """
            SELECT a.user_id, SUM(a.count) AS total, u.first_name, u.last_name
            FROM activity a LEFT JOIN users u ON u.user_id = a.user_id
            WHERE a.day >= ? GROUP BY a.user_id ORDER BY total DESC LIMIT ?
            """,
            (self.today(-(days - 1)), limit),
        ) as cur:
            return list(await cur.fetchall())

    async def ghost(self, days: int = 7) -> aiosqlite.Row | None:
        """La personne vue ce mois-ci qui a le moins parlé ces `days` derniers jours."""
        async with self.conn.execute(
            """
            SELECT u.user_id, u.first_name, u.last_name,
                   COALESCE((SELECT SUM(a.count) FROM activity a WHERE a.user_id = u.user_id AND a.day >= ?), 0) AS total
            FROM users u WHERE u.is_bot = 0 AND u.last_seen >= ?
            ORDER BY total ASC, u.last_seen ASC LIMIT 1
            """,
            (self.today(-(days - 1)), int(time.time()) - 30 * 86400),
        ) as cur:
            return await cur.fetchone()

    # --- Citations ---

    async def add_quote(
        self, user_id: int, author_name: str, text: str, said_at: int, message_id: int, saved_by: int
    ) -> int | None:
        """Retourne le numéro de la citation, ou None si ce message est déjà cité."""
        cur = await self.conn.execute(
            """
            INSERT OR IGNORE INTO quotes(user_id, author_name, text, said_at, message_id, saved_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, author_name, text, said_at, message_id, saved_by),
        )
        await self.conn.commit()
        return cur.lastrowid if cur.rowcount else None

    async def random_quote(self, user_id: int | None = None) -> aiosqlite.Row | None:
        query = "SELECT * FROM quotes" + (" WHERE user_id = ?" if user_id else "") + " ORDER BY RANDOM() LIMIT 1"
        async with self.conn.execute(query, (user_id,) if user_id else ()) as cur:
            return await cur.fetchone()

    async def get_quote(self, quote_id: int) -> aiosqlite.Row | None:
        async with self.conn.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)) as cur:
            return await cur.fetchone()

    async def delete_quote(self, quote_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM quotes WHERE id = ?", (quote_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    async def count_quotes(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) AS n FROM quotes") as cur:
            return (await cur.fetchone())["n"]

    # --- Anniversaires ---

    async def set_birthday(self, user_id: int, day: int, month: int) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO birthdays(user_id, day, month) VALUES (?, ?, ?)", (user_id, day, month)
        )
        await self.conn.commit()

    async def get_birthday(self, user_id: int) -> aiosqlite.Row | None:
        async with self.conn.execute("SELECT * FROM birthdays WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone()

    async def delete_birthday(self, user_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM birthdays WHERE user_id = ?", (user_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    async def all_birthdays(self) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            """
            SELECT b.*, u.first_name, u.last_name
            FROM birthdays b LEFT JOIN users u ON u.user_id = b.user_id
            """
        ) as cur:
            return list(await cur.fetchall())

    # --- Prison ---

    async def prisoners(self) -> list[aiosqlite.Row]:
        """Personnes dont la dernière action est un ban / mute (ou mute de jeu) encore en cours."""
        now = int(time.time())
        async with self.conn.execute(
            """
            SELECT a.*, u.first_name, u.last_name FROM actions a
            LEFT JOIN users u ON u.user_id = a.user_id
            WHERE a.id IN (
                SELECT MAX(id) FROM actions
                WHERE action IN ('ban', 'mute', 'jail', 'unban', 'unmute', 'kick')
                GROUP BY user_id
            )
            AND a.action IN ('ban', 'mute', 'jail') AND (a.until IS NULL OR a.until > ?)
            ORDER BY a.until IS NULL, a.until
            """,
            (now,),
        ) as cur:
            return list(await cur.fetchall())

    # --- Flocko ---

    async def get_flocko(self, user_id: int) -> aiosqlite.Row | None:
        async with self.conn.execute("SELECT * FROM flocko WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone()

    async def save_flocko(self, user_id: int, value: int) -> aiosqlite.Row:
        """Enregistre un tirage ; le record n'est remplacé que s'il est battu."""
        now = int(time.time())
        await self.conn.execute(
            """
            INSERT INTO flocko(user_id, last, last_at, best, best_at, rolls) VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                last = excluded.last,
                last_at = excluded.last_at,
                best_at = CASE WHEN excluded.best > flocko.best THEN excluded.best_at ELSE flocko.best_at END,
                best = MAX(flocko.best, excluded.best),
                rolls = flocko.rolls + 1
            """,
            (user_id, value, now, value, now),
        )
        await self.conn.commit()
        return await self.get_flocko(user_id)

    async def flocko_board(self, offset: int, limit: int) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            """
            SELECT f.*, u.first_name, u.last_name FROM flocko f LEFT JOIN users u ON u.user_id = f.user_id
            ORDER BY f.best DESC, f.best_at ASC LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ) as cur:
            return list(await cur.fetchall())

    async def flocko_players(self) -> int:
        async with self.conn.execute("SELECT COUNT(*) AS n FROM flocko") as cur:
            return (await cur.fetchone())["n"]

    async def flocko_rank(self, user_id: int) -> int | None:
        row = await self.get_flocko(user_id)
        if row is None:
            return None
        async with self.conn.execute(
            "SELECT COUNT(*) AS n FROM flocko WHERE best > ? OR (best = ? AND best_at < ?)",
            (row["best"], row["best"], row["best_at"]),
        ) as cur:
            return (await cur.fetchone())["n"] + 1
