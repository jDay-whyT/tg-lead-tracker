import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

import config
from bot import admin
from bot import sheets
from db import firestore as db

logger = logging.getLogger(__name__)


async def on_business_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bc = update.business_connection
    if bc is None:
        return

    connection_id = bc.id

    if not bc.is_enabled:
        await db.update_manager_status(connection_id, "disconnected")
        return

    user = bc.user
    manager_data = {
        "user_id": user.id,
        "username": user.username or "",
        "first_name": user.first_name or "",
        "status": "pending",
        "connected_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.save_manager(connection_id, manager_data)
    await admin.notify_admin(context.bot, manager_data, connection_id)
    logger.info("Manager registered: user_id=%s connection_id=%s", user.id, connection_id)


async def on_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.business_message
    if msg is None:
        return

    connection_id = msg.business_connection_id
    if not connection_id:
        return

    manager = await db.get_manager(connection_id)
    if not manager or manager.get("status") != "approved":
        return

    if msg.from_user is None or msg.from_user.id == manager["user_id"]:
        return

    text = msg.text or msg.caption or ""
    try:
        await sheets.append_lead(
            manager_username=manager.get("username", ""),
            lead_user=msg.from_user,
            message_text=text,
        )
        logger.info(
            "Lead logged: manager=@%s lead_id=%s",
            manager.get("username"),
            msg.from_user.id,
        )
    except Exception:
        logger.exception(
            "Sheets write failed: manager=@%s lead_id=%s",
            manager.get("username"),
            msg.from_user.id,
        )


async def on_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    data = query.data or ""
    if ":" not in data:
        return

    action, connection_id = data.split(":", 1)
    if action not in ("approve", "reject"):
        return

    manager = await db.get_manager(connection_id)
    if manager is None:
        await query.edit_message_text("Manager not found.")
        return

    status = "approved" if action == "approve" else "rejected"
    await db.update_manager_status(connection_id, status)

    label = "approved ✅" if status == "approved" else "rejected ❌"
    original_text = query.message.text if query.message else ""
    await query.edit_message_text(f"{original_text}\n\n→ {label}")

    manager_reply = "You are approved ✅" if status == "approved" else "Access denied ❌"
    try:
        await context.bot.send_message(chat_id=manager["user_id"], text=manager_reply)
    except Exception as e:
        logger.warning("Could not notify manager %s: %s", manager["user_id"], e)


async def cmd_managers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id != config.ADMIN_CHAT_ID:
        return

    managers = await db.list_managers()
    if not managers:
        await update.message.reply_text("No managers registered.")
        return

    lines = [
        f"@{m.get('username') or 'N/A'} | {m.get('first_name', '')} | "
        f"status: {m.get('status')} | cid: {m.get('connection_id')}"
        for m in managers
    ]
    await update.message.reply_text("\n".join(lines))
