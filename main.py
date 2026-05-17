import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import (
    Application,
    BusinessConnectionHandler,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

import bot.sheets as _sheets
import config
from bot.lego import import_lego
from bot.handlers import (
    cmd_delete,
    cmd_help,
    cmd_managers,
    cmd_reset,
    on_business_connection,
    on_business_message,
    on_callback_query,
    on_regular_message,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_ptb: Application | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ptb
    _ptb = Application.builder().token(config.BOT_TOKEN).build()
    _ptb.add_handler(BusinessConnectionHandler(on_business_connection))
    _ptb.add_handler(MessageHandler(filters.UpdateType.BUSINESS_MESSAGE, on_business_message))
    _ptb.add_handler(CallbackQueryHandler(on_callback_query))
    _ptb.add_handler(CommandHandler("managers", cmd_managers))
    _ptb.add_handler(CommandHandler("delete", cmd_delete))
    _ptb.add_handler(CommandHandler("help", cmd_help))
    _ptb.add_handler(CommandHandler("reset", cmd_reset))
    _ptb.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, on_regular_message))

    if not config.WEBHOOK_SECRET:
        logger.warning("WEBHOOK_SECRET is not set — /import/lego endpoint is unauthenticated")

    await asyncio.to_thread(_sheets.init_header)
    await _ptb.initialize()
    await _ptb.start()
    logger.info("Bot started")
    yield
    await _ptb.stop()
    await _ptb.shutdown()
    logger.info("Bot stopped")


app = FastAPI(lifespan=lifespan)


@app.post("/webhook")
async def webhook(request: Request) -> Response:
    if config.WEBHOOK_SECRET:
        token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if token != config.WEBHOOK_SECRET:
            return Response(status_code=403)

    body = await request.json()
    update = Update.de_json(body, _ptb.bot)
    logger.info("RAW UPDATE: %s", body)
    await _ptb.process_update(update)
    return Response(status_code=200)


@app.post("/import/lego")
async def import_lego_endpoint(request: Request) -> Response:
    if config.WEBHOOK_SECRET:
        token = request.headers.get("X-Webhook-Secret", "")
        if token != config.WEBHOOK_SECRET:
            return Response(status_code=403)
    if _ptb is None:
        return Response(status_code=503)
    count = await import_lego(_ptb.bot)
    return Response(content=f'{{"imported":{count}}}', media_type="application/json")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
