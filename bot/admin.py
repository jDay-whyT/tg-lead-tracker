from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

import config


def approval_keyboard(connection_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve ✅", callback_data=f"approve:{connection_id}"),
            InlineKeyboardButton("Reject ❌", callback_data=f"reject:{connection_id}"),
        ]
    ])


async def notify_admin(bot: Bot, manager: dict, connection_id: str) -> None:
    username = manager.get("username") or "N/A"
    user_id = manager["user_id"]
    crm_name = manager.get("crm_name") or "N/A"
    text = (
        f"New manager connected:\n"
        f"CRM ник: {crm_name}\n"
        f"@{username} | user_id: {user_id}"
    )
    await bot.send_message(
        chat_id=config.ADMIN_CHAT_ID,
        text=text,
        reply_markup=approval_keyboard(connection_id),
    )
