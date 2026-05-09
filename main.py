import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import (
    Application,
    BusinessConnectionHandler,
    BusinessMessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters,
)

import config
from bot.handlers import (
    cmd_managers,
    on_business_connection,
    on_business_message,
    on_callback_query,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_ptb: Application | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ptb
    _ptb = Application.builder().token(config.BOT_TOKEN).build()
    _ptb.add_handler(BusinessConnectionHandler(on_business_connection))
    _ptb.add_handler(BusinessMessageHandler(filters.ALL, on_business_message))
    _ptb.add_handler(CallbackQueryHandler(on_callback_query))
    _ptb.add_handler(CommandHandler("managers", cmd_managers))

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
    await _ptb.process_update(update)
    return Response(status_code=200)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
