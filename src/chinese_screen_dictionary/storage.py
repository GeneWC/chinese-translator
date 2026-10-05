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
        """)
        if self.db.execute("PRAGMA user_version").fetchone()[0] < 2:
            with self.db:
                # Old IDs included one arbitrary traditional form, splitting
                # explicit variants. Merge without counting a lookup twice.
                for row in self.db.execute("SELECT * FROM entries WHERE key LIKE 'cedict:%|%'").fetchall():
                    key = f'cedict:{row["simplified"]}'
                    self._save_entry(key, row["simplified"], row["traditional"], row["pinyin"],
                                     json.loads(row["definitions"]), row["is_character"])
                    self.db.execute("""INSERT OR IGNORE INTO occurrences
                        SELECT lookup_id, ?, surface FROM occurrences WHERE entry_key=?""", (key, row["key"]))
                    self.db.execute("DELETE FROM entries WHERE key=?", (row["key"],))
                self.db.execute("PRAGMA user_version=2")

    def _save_entry(self, key, simplified, traditional, pinyin, definitions, is_character):
        previous = self.db.execute("SELECT traditional, definitions FROM entries WHERE key=?", (key,)).fetchone()
        if previous:
            traditional = " / ".join(dict.fromkeys(previous["traditional"].split(" / ") + traditional.split(" / ")))
            for sense in json.loads(previous["definitions"]):
                if sense not in definitions:
                    definitions.append(sense)
        pinyin = " / ".join(dict.fromkeys(sense["pinyin"] for sense in definitions)) or pinyin
        self.db.execute("""INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET traditional=excluded.traditional,
                pinyin=excluded.pinyin, definitions=excluded.definitions""",
            (key, simplified, traditional, pinyin, json.dumps(definitions, ensure_ascii=False), is_character))

    def replace_lookup(self, lookup_id: str, result: Analysis):
        now = datetime.now(timezone.utc).isoformat()
        with self.db:
            self.db.execute("""INSERT INTO lookups VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET text=excluded.text, translation=excluded.translation""",
                (lookup_id, result.text, result.translation, now))
            self.db.execute("DELETE FROM occurrences WHERE lookup_id=?", (lookup_id,))
            for word in result.words:
                if not word.save:
                    continue
                definitions = [{"pinyin": sense.pinyin, "definitions": list(sense.definitions)} for sense in word.senses]
                self._save_entry(word.key, word.simplified, word.traditional, word.pinyin, definitions, len(word.surface) == 1)
                self.db.execute("INSERT OR IGNORE INTO occurrences VALUES (?, ?, ?)", (lookup_id, word.key, word.surface))
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
