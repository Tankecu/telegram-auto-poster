import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import bot.scheduler as scheduler

_tmp = tempfile.mkdtemp()
mock.patch.object(scheduler, "DB_PATH", Path(_tmp) / "test.db").start()

from bot.scheduler import (  # noqa: E402
    cancel_post,
    due_posts,
    get_db,
    mark_failed_attempt,
    mark_published,
    minutes_until,
    queue_of,
    queue_post,
    resolve_time,
)

NOW = datetime(2026, 9, 13, 12, 0)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_db()
        self.conn.execute("DELETE FROM posts")
        self.conn.commit()

    def test_resolve_quick_options(self):
        self.assertEqual(resolve_time("in_1h", NOW), NOW + timedelta(hours=1))
        self.assertEqual(resolve_time("tonight_18", NOW), NOW.replace(hour=18, minute=0))
        # 23:50 + tonight_18 → tomorrow 18:00, never the past
        late = NOW.replace(hour=23, minute=50)
        self.assertEqual(resolve_time("tonight_18", late), late.replace(day=14, hour=18, minute=0))

    def test_resolve_custom_time_rolls_to_tomorrow(self):
        self.assertEqual(resolve_time("09:15", NOW), (NOW + timedelta(days=1)).replace(hour=9, minute=15))
        self.assertEqual(resolve_time("14:30", NOW), NOW.replace(hour=14, minute=30))
        with self.assertRaises(ValueError):
            resolve_time("25:99", NOW)

    def test_due_posts_only_queued_and_past(self):
        pid = queue_post(self.conn, owner_id="u", text="hello", publish_at=NOW - timedelta(minutes=5))
        future = queue_post(self.conn, owner_id="u", text="later", publish_at=NOW + timedelta(hours=2))
        due = due_posts(self.conn, NOW)
        self.assertEqual([r["id"] for r in due], [pid])

    def test_retry_then_fail(self):
        pid = queue_post(self.conn, owner_id="u", text="hello", publish_at=NOW - timedelta(minutes=1))
        mark_failed_attempt(self.conn, pid, "network down")
        self.assertEqual(self.conn.execute("SELECT status FROM posts WHERE id=?", (pid,)).fetchone()[0], "queued")
        mark_failed_attempt(self.conn, pid, "network down")
        self.assertEqual(self.conn.execute("SELECT status FROM posts WHERE id=?", (pid,)).fetchone()[0], "queued")
        mark_failed_attempt(self.conn, pid, "network down")
        self.assertEqual(self.conn.execute("SELECT status FROM posts WHERE id=?", (pid,)).fetchone()[0], "failed")
        # failed posts are never picked up again
        self.assertEqual(due_posts(self.conn, NOW), [])

    def test_publish_and_cancel(self):
        pid = queue_post(self.conn, owner_id="u1", text="hello", publish_at=NOW - timedelta(minutes=1))
        mark_published(self.conn, pid)
        self.assertEqual(queue_of(self.conn, "u1"), [])
        pid2 = queue_post(self.conn, owner_id="u1", text="second", publish_at=NOW + timedelta(hours=1))
        self.assertTrue(cancel_post(self.conn, pid2, "u1"))
        self.assertFalse(cancel_post(self.conn, pid2, "u1"))  # already gone

    def test_minutes_until(self):
        self.assertEqual(minutes_until("2026-09-13 12:30", NOW), 30)
        self.assertEqual(minutes_until("2026-09-13 11:00", NOW), 0)


if __name__ == "__main__":
    unittest.main()
