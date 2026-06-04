import logging
from datetime import datetime, timezone, timedelta

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
        username = bc.user.username or bc.user.first_name or str(bc.user.id)
        for admin_id in config.ADMIN_CHAT_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"Manager @{username} disconnected the bot ⚠️",
            )
        return

    user = bc.user
    manager_data = {
        "user_id": user.id,
        "username": user.username or "",
        "first_name": user.first_name or "",
        "status": "awaiting_crm_name",
        "connected_at": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
    }
    await db.save_manager(connection_id, manager_data)
    await context.bot.send_message(
        chat_id=user.id,
        text="Привет! Введи свой CRM ник (например: User HR_2121)",
    )
    logger.info("Manager registered: user_id=%s connection_id=%s", user.id, connection_id)


async def on_regular_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("chat_id: %s", update.effective_chat.id)
    msg = update.message
    if msg is None or msg.from_user is None or msg.text is None:
        return

    result = await db.get_manager_by_user_id(msg.from_user.id)
    if result is None:
        await msg.reply_text("Привет! Подключи бота через Настройки → Автоматизация чатов")
        return

    connection_id, manager = result
    if manager.get("status") != "awaiting_crm_name":
        return

    crm_name = msg.text.strip()
    await db.update_manager_crm(connection_id, crm_name)
    manager["crm_name"] = crm_name
    await admin.notify_admin(context.bot, manager, connection_id)
    await msg.reply_text("Спасибо! Ваша заявка отправлена на рассмотрение.")
    logger.info("CRM name set: user_id=%s crm_name=%s", msg.from_user.id, crm_name)


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

    if msg.from_user is None:
        return

    is_outgoing = msg.from_user.id == manager["user_id"]

    if is_outgoing:
        if msg.text is None or msg.from_user.is_bot:
            return
        lead_user_id = msg.chat.id
        logger.info(
            "Outgoing business_message: from_user.id=%s manager.user_id=%s chat.id=%s text=%r date=%s",
            msg.from_user.id,
            manager["user_id"],
            msg.chat.id,
            msg.text[:80],
            msg.date,
        )
        now = datetime.now(timezone.utc) + timedelta(hours=3)
        if not await db.lead_exists(connection_id, lead_user_id):
            username = getattr(msg.chat, "username", "") or ""
            first = getattr(msg.chat, "first_name", "") or ""
            last = getattr(msg.chat, "last_name", "") or ""
            full_name = f"{first} {last}".strip()
            tg_value = f"@{username}" if username else full_name
            try:
                row_number = await sheets.append_lego_lead({
                    "Стейдж HR, точно так,как в CRM": manager.get("crm_name", ""),
                    "Дата": now.strftime("%d.%m.%Y"),
                    "Время": now.strftime("%H:%M"),
                    "Telegram": tg_value,
                    "Должность": "manager",
                })
                await db.mark_lead_seen(connection_id, lead_user_id, row_number)
                logger.info("Outgoing new contact logged: lead_id=%s row=%s", lead_user_id, row_number)
            except Exception:
                logger.exception("Failed to write outgoing contact: lead_id=%s", lead_user_id)
        else:
            lead = await db.get_lead(connection_id, lead_user_id)
            if lead and not lead.get("replied") and lead.get("row_number"):
                try:
                    await sheets.update_date_svyazi(lead["row_number"], now)
                    await db.mark_lead_replied(connection_id, lead_user_id)
                    logger.info("Дата связи updated: lead_id=%s row=%s", lead_user_id, lead["row_number"])
                except Exception:
                    logger.exception("Failed to update Дата связи: lead_id=%s", lead_user_id)
            else:
                logger.info("Outgoing: lead already handled for chat.id=%s — skipping", lead_user_id)
        return

    lead_user_id = msg.from_user.id
    existing_lead = await db.get_lead(connection_id, lead_user_id)
    if existing_lead is not None:
        if not existing_lead.get("replied") and existing_lead.get("row_number"):
            now = datetime.now(timezone.utc) + timedelta(hours=3)
            try:
                await sheets.update_date_svyazi(existing_lead["row_number"], now)
                await db.mark_lead_replied(connection_id, lead_user_id)
                logger.info("Lead replied, Дата связи updated: lead_id=%s row=%s", lead_user_id, existing_lead["row_number"])
            except Exception:
                logger.exception("Failed to update Дата связи on reply: lead_id=%s", lead_user_id)
        else:
            logger.info("Duplicate lead skipped: lead_id=%s", lead_user_id)
        return

    text = msg.text or msg.caption or ""
    try:
        row_number = await sheets.append_lead(
            crm_name=manager.get("crm_name", ""),
            lead_user=msg.from_user,
            message_text=text,
        )
        await db.mark_lead_seen(connection_id, msg.from_user.id, row_number)
        logger.info(
            "Lead logged: manager=@%s lead_id=%s row=%s",
            manager.get("username"),
            msg.from_user.id,
            row_number,
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

    data = query.data or ""
    if ":" not in data:
        return

    action, connection_id = data.split(":", 1)
    if action not in ("approve", "reject"):
        return

    manager = await db.get_manager(connection_id)
    if manager is None:
        await query.answer("Manager not found.")
        return

    if manager.get("status") in ("approved", "rejected"):
        await query.answer("Уже обработано ✅")
        return

    await query.answer()
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


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id not in config.ADMIN_CHAT_IDS:
        return
    await update.message.reply_text(
        "/managers — список менеджеров со статусом и датой подключения\n"
        "/delete @username — удалить менеджера из базы\n"
        "/reset — сбросить CRM ник (для менеджеров)\n"
        "/help — список команд"
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None:
        return
    result = await db.get_manager_by_user_id(update.effective_user.id)
    if result is None:
        await update.message.reply_text("Ты не зарегистрирован как менеджер.")
        return
    connection_id, _ = result
    await db.reset_manager_crm(connection_id)
    await update.message.reply_text("Введи новый CRM ник")
    logger.info("Manager reset CRM: user_id=%s", update.effective_user.id)


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id not in config.ADMIN_CHAT_IDS:
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /delete @username")
        return

    username = args[0].lstrip("@")
    deleted = await db.delete_manager_by_username(username)
    if deleted:
        await update.message.reply_text(f"Manager @{username} deleted ✅")
        logger.info("Manager deleted: @%s", username)
    else:
        await update.message.reply_text(f"Manager @{username} not found ❌")


async def cmd_managers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.effective_user.id not in config.ADMIN_CHAT_IDS:
        return

    managers = await db.list_managers()
    if not managers:
        await update.message.reply_text("No managers registered.")
        return

    _status_emoji = {"approved": "✅", "rejected": "❌", "pending": "⏳", "disconnected": "🔌"}

    lines = []
    for m in managers:
        username = f"@{m.get('username')}" if m.get("username") else m.get("first_name") or "N/A"
        status = m.get("status", "unknown")
        emoji = _status_emoji.get(status, "❓")
        connected_at = (m.get("connected_at") or "")[:10]
        lines.append(f"{username} — {emoji} {status} — {connected_at}")

    await update.message.reply_text("\n".join(lines))
