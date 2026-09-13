"""aiogram handlers: send a post, pick when, manage the queue."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .scheduler import (
    QUICK_OPTIONS,
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

logger = logging.getLogger(__name__)
router = Router()


class Posting(StatesGroup):
    waiting_time = State()


def _time_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"when:{cid}")] for cid, label in QUICK_OPTIONS]
    rows.append([InlineKeyboardButton(text="⏰ Custom time (HH:MM)", callback_data="when:custom")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Hi! 👋 I publish scheduled posts to *your* channel.\n\n"
        "1. Send me the text of the post\n"
        "2. Pick when it goes out\n"
        "3. Forget about it — I'll publish and confirm\n\n"
        "Useful: /queue — what's scheduled, /cancel 12 — unschedule post #12.",
        parse_mode="Markdown",
    )


@router.message(Command("queue"))
async def show_queue(message: Message) -> None:
    rows = queue_of(get_db(), str(message.from_user.id))
    if not rows:
        await message.answer("The queue is empty. Send me a post text to schedule one.")
        return
    lines = [
        f"#{r['id']} · in {minutes_until(r['publish_at'])} min\n{r['text'][:80]}{'…' if len(r['text']) > 80 else ''}"
        for r in rows
    ]
    await message.answer("📋 Upcoming posts:\n\n" + "\n\n".join(lines))


@router.message(Command("cancel"))
async def cancel(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /cancel 12")
        return
    ok = cancel_post(get_db(), int(parts[1]), str(message.from_user.id))
    await message.answer("Cancelled ✓" if ok else "That post isn't yours or is already gone.")


@router.message(F.text)
async def new_post(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        await message.answer("Unknown command. Send a post text, or use /queue, /cancel N.")
        return
    await state.set_state(Posting.waiting_time)
    await state.update_data(text=text)
    await message.answer("When should this go out?", reply_markup=_time_kb())


@router.callback_query(Posting.waiting_time, F.data.startswith("when:"))
async def pick_time(cb: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    choice = cb.data.split(":", 1)[1]
    data = await state.get_data()

    if choice == "custom":
        await cb.message.edit_text("Send the time as HH:MM (e.g. 18:30) — today or tomorrow, whichever is next.")
        await cb.answer()
        return

    try:
        publish_at = resolve_time(choice)
    except ValueError:
        await cb.answer("Unknown option", show_alert=True)
        return

    post_id = queue_post(get_db(), owner_id=str(cb.from_user.id), text=data["text"], publish_at=publish_at)
    await state.clear()
    await cb.message.edit_text(
        f"📌 Scheduled as #{post_id} — goes out {publish_at.strftime('%a %d %b at %H:%M')}.\n"
        "I'll confirm here when it's published."
    )
    await cb.answer()


@router.message(Posting.waiting_time, F.text)
async def custom_time(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        publish_at = resolve_time((message.text or "").strip())
    except ValueError:
        await message.answer("That's not HH:MM. Try again, e.g. 18:30.")
        return

    post_id = queue_post(get_db(), owner_id=str(message.from_user.id), text=data["text"], publish_at=publish_at)
    await state.clear()
    await message.answer(
        f"📌 Scheduled as #{post_id} — goes out {publish_at.strftime('%a %d %b at %H:%M')}."
    )


async def publish(post_row, channel_id: str, bot: Bot | None) -> bool:
    """One publish attempt. Demo-safe: with bot=None it only logs."""
    if bot is None:
        print(f"[demo] 📤 published to channel {channel_id or 'demo-channel'}:\n   {post_row['text'][:100]}")
        return True
    try:
        await bot.send_message(int(channel_id), post_row["text"])
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("publish failed for #%s: %s", post_row["id"], e)
        return False


async def scheduler_loop(bot: Bot | None, channel_id: str, owner_chat: str | None) -> None:
    """Publishes due posts; retries failures up to 3 times with a 2-minute delay."""
    while True:
        conn = get_db()
        try:
            for row in due_posts(conn):
                ok = await publish(row, channel_id, bot)
                if ok:
                    mark_published(conn, row["id"])
                    if bot and owner_chat:
                        try:
                            await bot.send_message(int(owner_chat), f"✅ Post #{row['id']} published.")
                        except Exception:  # noqa: BLE001
                            pass
                else:
                    mark_failed_attempt(conn, row["id"], "send_message failed")
        except Exception:  # noqa: BLE001
            logger.exception("scheduler iteration failed")
        finally:
            conn.close()
        await asyncio.sleep(20)
