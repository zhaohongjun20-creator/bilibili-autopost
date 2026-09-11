"""SQLite 状态存储：素材去重 + 投稿状态流转。"""
import sqlite3, os, datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    pexels_id   INTEGER PRIMARY KEY,
    keyword     TEXT,
    source_url  TEXT,
    title       TEXT DEFAULT '',
    status      TEXT DEFAULT 'fetched',   -- fetched|published|failed
    bvid        TEXT DEFAULT '',
    error       TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now','localtime')),
    published_at TEXT DEFAULT ''
);
"""

class Store:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def is_published(self, pexels_id: int) -> bool:
        row = self.conn.execute(
            "SELECT status FROM videos WHERE pexels_id=?", (pexels_id,)
        ).fetchone()
        return bool(row and row["status"] == "published")

    def get_bvid(self, pexels_id: int) -> str:
        row = self.conn.execute(
            "SELECT bvid FROM videos WHERE pexels_id=?", (pexels_id,)
        ).fetchone()
        return row["bvid"] if row else ""

    def record_fetched(self, pexels_id: int, keyword: str, source_url: str):
        self.conn.execute(
            "INSERT INTO videos (pexels_id, keyword, source_url) VALUES (?,?,?)",
            (pexels_id, keyword, source_url),
        )
        self.conn.commit()

    def mark_published(self, pexels_id: int, bvid: str):
        self.conn.execute(
            "UPDATE videos SET status='published', bvid=?, published_at=? WHERE pexels_id=?",
            (bvid, datetime.datetime.now().isoformat(timespec="seconds"), pexels_id),
        )
        self.conn.commit()

    def mark_failed(self, pexels_id: int, error: str):
        self.conn.execute(
            "UPDATE videos SET status='failed', error=? WHERE pexels_id=?",
            (error, pexels_id),
        )
        self.conn.commit()

    def pending_retry(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM videos WHERE status='failed' ORDER BY created_at LIMIT 5"
        ).fetchall()]

    def known_ids(self) -> set:
        return {r[0] for r in self.conn.execute("SELECT pexels_id FROM videos").fetchall()}
