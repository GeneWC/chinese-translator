import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .types import Analysis


class VocabularyStore:
    """Used only on its owner thread. Counts are derived from lookup membership."""

    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS lookups (
                id TEXT PRIMARY KEY, text TEXT NOT NULL, translation TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS entries (
                key TEXT PRIMARY KEY, simplified TEXT NOT NULL, traditional TEXT NOT NULL,
                pinyin TEXT NOT NULL, definitions TEXT NOT NULL, is_character INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS occurrences (
                lookup_id TEXT REFERENCES lookups(id) ON DELETE CASCADE,
                entry_key TEXT REFERENCES entries(key) ON DELETE CASCADE,
                surface TEXT NOT NULL, PRIMARY KEY (lookup_id, entry_key)
            );
            CREATE INDEX IF NOT EXISTS occurrences_entry ON occurrences(entry_key);
            PRAGMA user_version=1;
        """)

    def replace_lookup(self, lookup_id: str, result: Analysis):
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            self.db.execute("""INSERT INTO lookups VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET text=excluded.text, translation=excluded.translation""",
                (lookup_id, result.text, result.translation, now))
            self.db.execute("DELETE FROM occurrences WHERE lookup_id=?", (lookup_id,))
            seen = set()
            for word in result.words:
                if not word.save or word.key in seen:
                    continue
                seen.add(word.key)
                definitions = json.dumps([
                    {"pinyin": sense.pinyin, "definitions": sense.definitions} for sense in word.senses
                ], ensure_ascii=False)
                self.db.execute("""INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET pinyin=excluded.pinyin, definitions=excluded.definitions""",
                    (word.key, word.simplified, word.traditional, word.pinyin, definitions, len(word.surface) == 1))
                self.db.execute("INSERT INTO occurrences VALUES (?, ?, ?)", (lookup_id, word.key, word.surface))
            self.db.execute("DELETE FROM entries WHERE NOT EXISTS (SELECT 1 FROM occurrences WHERE entry_key=entries.key)")
            self.db.execute("DELETE FROM lookups WHERE id=? AND NOT EXISTS (SELECT 1 FROM occurrences WHERE lookup_id=lookups.id)", (lookup_id,))

    def list_entries(self, characters=False, search=""):
        # Treat search as literal input, including SQL wildcard characters.
        pattern = "%" + search.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        return [dict(row) for row in self.db.execute("""
            SELECT e.*, COUNT(*) AS count, MAX(l.created_at) AS last_seen
            FROM entries e JOIN occurrences o ON e.key=o.entry_key JOIN lookups l ON l.id=o.lookup_id
            WHERE e.is_character=? AND (
                e.simplified LIKE ? ESCAPE '!' OR e.traditional LIKE ? ESCAPE '!' OR
                e.pinyin LIKE ? ESCAPE '!' OR e.definitions LIKE ? ESCAPE '!')
            GROUP BY e.key ORDER BY count DESC, last_seen DESC, e.simplified
        """, (int(characters), pattern, pattern, pattern, pattern))]

    def contexts(self, key: str):
        return [dict(row) for row in self.db.execute("""
            SELECT l.text, l.translation, l.created_at, o.surface FROM lookups l
            JOIN occurrences o ON l.id=o.lookup_id WHERE o.entry_key=? ORDER BY l.created_at DESC
        """, (key,))]

    def delete_entry(self, key: str):
        with self.db:
            self.db.execute("DELETE FROM entries WHERE key=?", (key,))
            self.db.execute("DELETE FROM lookups WHERE NOT EXISTS (SELECT 1 FROM occurrences WHERE lookup_id=lookups.id)")

    def close(self):
        self.db.close()
