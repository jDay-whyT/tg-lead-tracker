import html
import logging
from datetime import datetime

from telegram import Bot

import config
from bot.sheets import append_lego_lead, read_range
from db.firestore import get_lego_state, set_lego_state

logger = logging.getLogger(__name__)

_FORM_SHEET = "YD forma 1"

# Column names as they appear in the form sheet header row.
# Adjust these to match the actual Google Sheet column headers.
_COL_CREATED_TIME = "created_time"
_COL_FULL_NAME = "полное_имя"
_COL_TELEGRAM = "ваш_телеграмм_юзернейи_или_номер_телефона:"
_COL_PHONE = "номер_телефона"
_COL_PLATFORM = "platform"
_COL_AGE = "какой_ваш_возраст?"
_COL_EXPERIENCE = "был_ли_опыт_чаттером_?"
_COL_ENGLISH = "какое_у_вас_знание_английского_языка?"
_COL_PC = "есть_ли_у_вас_пк\\ноутбук?_нужен_для_работы"


def _safe(row: list, idx: int) -> str:
    return row[idx] if idx >= 0 and idx < len(row) else ""


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


async def import_lego(bot: Bot) -> int:
    state = await get_lego_state()
    now = datetime.utcnow()

    if state is None:
        await set_lego_state({"last_processed_created_time": now.isoformat(), "rr_counter": 0})
        logger.info("lego_state initialized, no rows processed")
        return 0

    last_dt = _naive(datetime.fromisoformat(state["last_processed_created_time"]))
    rr_counter = state.get("rr_counter", 0)

    rows = await read_range(config.LEGO_FORM_ID, f"'{_FORM_SHEET}'!A1:Z10000")
    if not rows:
        return 0

    header = rows[0]

    def idx(col_name: str) -> int:
        return header.index(col_name) if col_name in header else -1

    ct_idx = idx(_COL_CREATED_TIME)
    if ct_idx < 0:
        logger.error("'%s' column not found in form header: %s", _COL_CREATED_TIME, header)
        return 0

    fn_idx = idx(_COL_FULL_NAME)
    tg_idx = idx(_COL_TELEGRAM)
    ph_idx = idx(_COL_PHONE)
    pl_idx = idx(_COL_PLATFORM)
    ag_idx = idx(_COL_AGE)
    ex_idx = idx(_COL_EXPERIENCE)
    en_idx = idx(_COL_ENGLISH)
    pc_idx = idx(_COL_PC)

    new_rows: list[tuple[datetime, list]] = []
    for row in rows[1:]:
        ct_str = _safe(row, ct_idx)
        if not ct_str:
            continue
        try:
            ct = _naive(datetime.fromisoformat(ct_str))
        except ValueError:
            logger.warning("Cannot parse created_time: %r", ct_str)
            continue
        if ct > last_dt:
            new_rows.append((ct, row))

    if not new_rows:
        return 0

    new_rows.sort(key=lambda x: x[0])
    max_ct = new_rows[-1][0]
    hr_list = config.HR_LIST
    processed = 0

    for ct, row in new_rows:
        hr_name, tg_username = hr_list[rr_counter % len(hr_list)]
        rr_counter += 1

        full_name = _safe(row, fn_idx)
        telegram = _safe(row, tg_idx)
        phone = _safe(row, ph_idx)
        platform = _safe(row, pl_idx)
        age = _safe(row, ag_idx)
        experience = _safe(row, ex_idx)
        english = _safe(row, en_idx)
        pc = _safe(row, pc_idx)

        tg_display = f"@{telegram.lstrip('@')}" if telegram else full_name

        await append_lego_lead({
            "Стейдж HR, точно так,как в CRM": hr_name,
            "Дата": ct.strftime("%d.%m.%Y"),
            "Имя Лида": full_name,
            "Telegram": tg_display,
            "Телефон": phone,
            "Должность": "manager",
            "Источник": "FB Ru serbia lego",
        })

        text = (
            f"HR: <b>{html.escape(hr_name)}</b>\n"
            f" └ {html.escape(tg_username)}\n"
            f"    └ FB Ru serbia lego\n"
            f"\n"
            f"From: <b>{html.escape(platform)}</b>\n"
            f"Age: <b>{html.escape(age)}</b>\n"
            f"EXP: <b>{html.escape(experience)}</b>\n"
            f"EN: <b>{html.escape(english)}</b>\n"
            f"PC: <b>{html.escape(pc)}</b>\n"
            f"\n"
            f"👤 {html.escape(tg_display)} | <b>{html.escape(full_name)}</b>"
        )
        await bot.send_message(chat_id=config.GROUP_CHAT_ID, text=text, parse_mode="HTML")
        processed += 1

    await set_lego_state({
        "last_processed_created_time": max_ct.isoformat(),
        "rr_counter": rr_counter,
    })
    logger.info("lego import: processed %d rows", processed)
    return processed
