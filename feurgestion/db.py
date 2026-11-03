import json
import os
import time

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
"""

SANCTIONS = ("ban", "unban", "mute", "unmute", "kick")


def full_name(first: str | None, last: str | None) -> str:
    return " ".join(part for part in (first, last) if part) or "Sans nom"


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self.conn: aiosqlite.Connection | None = None

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

    async def track_user(self, user: User, active: bool) -> None:
        """Enregistre un utilisateur vu. `active` = il vient d'envoyer un message."""
        now = int(time.time())
        username = user.username
        name = full_name(user.first_name, user.last_name)

        existing = await self.get_user(user.id)
        if existing is None or (
            existing["username"] != username
            or full_name(existing["first_name"], existing["last_name"]) != name
        ):
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
        await self.conn.commit()

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

    async def name_history(self, user_id: int, limit: int = 5) -> list[aiosqlite.Row]:
        async with self.conn.execute(
            "SELECT * FROM name_history WHERE user_id = ? ORDER BY seen_at DESC LIMIT ?",
            (user_id, limit),
        ) as cur:
            return list(await cur.fetchall())

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
