"""Offline demo: schedules a post a few seconds ahead and "publishes" it.

No BOT_TOKEN needed.  Run:  python demo/run_demo.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# point the DB at a temp file so the demo never touches real data
import bot.scheduler as scheduler  # noqa: E402

tmp = tempfile.mkdtemp()
mock.patch.object(scheduler, "DB_PATH", Path(tmp) / "demo.db").start()

from bot.handlers import publish  # noqa: E402
from bot.scheduler import due_posts, get_db, mark_published, queue_post, resolve_time  # noqa: E402


async def main() -> None:
    print("=" * 62)
    print("TELEGRAM AUTO-POSTER — demo (offline)")
    print("Schedules a post ~5 seconds ahead, then 'publishes' it.")
    print("=" * 62)

    conn = get_db()
    post_text = (
        "🔥 Friday special at Demo Bistro!\n\n"
        "Wood-oven risotto + a glass of house wine for €18, tonight from 18:00.\n"
        "Table for two? Call +371 2000-0000."
    )
    when = datetime.now() + timedelta(seconds=5)
    post_id = queue_post(conn, owner_id="demo-owner", text=post_text, publish_at=when)
    print(f"\n[1] queued post #{post_id} for {when.strftime('%H:%M:%S')}")

    class FakeRow(dict):
        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    row = dict(conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone())

    print("[2] waiting for the scheduled moment…")
    while datetime.now() < when:
        time.sleep(0.5)

    ok = await publish(row, channel_id="demo-channel", bot=None)
    if ok:
        mark_published(conn, post_id)
        print(f"[3] ✅ post #{post_id} marked published — the owner would get a confirmation in Telegram")

    print("\n— queue state —")
    print("due posts now:", len(due_posts(conn)))
    print("status:", conn.execute("SELECT status FROM posts WHERE id = ?", (post_id,)).fetchone()[0])
    print("\nDemo finished. Live bot: fill .env (BOT_TOKEN, CHANNEL_ID) and run `python -m bot`.")


if __name__ == "__main__":
    asyncio.run(main())
