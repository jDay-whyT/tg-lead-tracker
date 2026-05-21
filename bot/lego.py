import asyncio
import html
import logging
import re
from datetime import datetime, timezone

from telegram import Bot
from telegram.error import RetryAfter

import config
from bot.sheets import append_lego_lead, read_range
from db.firestore import get_lego_state, set_lego_state

logger = logging.getLogger(__name__)

_SHEETS = [
    {
        "name": "YD forma 1",
        "source": "YD Lego 1",
        "type": "yd",
        "cols": {
            "created_time": "created_time",
            "full_name": "полное_имя",
            "telegram": "ваш_телеграмм_юзернейи_или_номер_телефона:",
            "phone": "номер_телефона",
            "platform": "platform",
            "age": "какой_ваш_возраст?",
            "experience": "был_ли_опыт_чаттером_?",
            "english": "какое_у_вас_знание_английского_языка?",
            "pc": "есть_ли_у_вас_пк\\ноутбук?_нужен_для_работы",
        },
    },
    {
        "name": "YD Smurf",
        "source": "YD Smurf",
        "type": "yd",
        "cols": {
            "created_time": "created_time",
            "full_name": "full_name",
            "telegram": "ваш_телеграмм_юзернейи_или_номер_телефона:",
            "phone": "phone_number",
            "platform": "platform",
            "age": "какой_ваш_возраст?",
            "experience": "был_ли_опыт_чаттером_?",
            "english": "какое_у_вас_знание_английского_языка?",
            "pc": "есть_ли_у_вас_пк\\ноутбук?_нужен_для_работы",
        },
    },
    {
        "name": "Smurf Belgrade ru",
        "source": "Smurf BG ru",
        "type": "belgrade",
        "cols": {
            "created_time": "created_time",
            "platform": "platform",
            "age": "какой_ваш_возраст?",
            "city": "в_каком_городе_вы_находитесь?",
            "english": "уровень_владения_английским_языком:",
            "office": "готовы_ли_вы_работать_в_офисе_в_белграде?",
            "night_shifts": "устраивает_ли_вас_график_с_ночными_сменами?",
            "telegram": "ваш_тг_юзернейм_или_номер_тел.",
            "full_name": "full_name",
            "phone": "phone_number",
        },
    },
    {
        "name": "YD Lego GEO",
        "source": "YD Lego GEO",
        "type": "yd_geo",
        "cols": {
            "created_time": "created_time",
            "adset_name": "adset_name",
            "full_name": "full_name",
            "telegram": "ваш_телеграмм_юзернейи_или_номер_телефона:",
            "phone": "phone_number",
            "platform": "platform",
            "age": "какой_ваш_возраст?",
            "experience": "был_ли_опыт_чаттером_?",
            "english": "какое_у_вас_знание_английского_языка?",
            "pc": "есть_ли_у_вас_пк\\ноутбук?_нужен_для_работы",
        },
    },
]


def _safe(row: list, idx: int) -> str:
    return row[idx] if 0 <= idx < len(row) else ""


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_tg(raw: str, fallback: str) -> str:
    s = raw.strip()
    if not s:
        return fallback
    if re.match(r'^[+\d][\d\s\-()]{6,}$', s):
        return s  # looks like a phone number, keep as-is
    m = re.search(r'@?([\w]{3,})', s)
    return f"@{m.group(1)}" if m else fallback


def _get(row: list, header: list, cols: dict, key: str) -> str:
    col_name = cols.get(key, "")
    if not col_name or col_name not in header:
        return ""
    return _safe(row, header.index(col_name))


async def import_lego(bot: Bot) -> int:
    state = await get_lego_state()
    now = datetime.now(timezone.utc)

    if state is None:
        await set_lego_state({"last_processed_created_time": now.isoformat(), "rr_counter": 0})
        logger.info("lego_state initialized, no rows processed")
        return 0

    last_dt = _as_utc(datetime.fromisoformat(state["last_processed_created_time"]))
    rr_counter = state.get("rr_counter", 0)

    all_new: list[tuple[datetime, list, list, dict]] = []

    for sheet in _SHEETS:
        try:
            rows = await read_range(config.LEGO_FORM_ID, f"'{sheet['name']}'!A1:Z10000")
        except Exception as exc:
            logger.error("Failed to read sheet '%s': %s — skipping", sheet["name"], exc)
            continue
        logger.info("Sheet '%s': %d raw rows (incl header)", sheet["name"], len(rows))
        if not rows:
            continue
        header = rows[0]
        ct_col = sheet["cols"]["created_time"]
        if ct_col not in header:
            logger.error("'%s' not in header for sheet '%s'; header=%s", ct_col, sheet["name"], header)
            continue
        ct_idx = header.index(ct_col)
        skipped_empty = skipped_old = skipped_parse = 0
        for row in rows[1:]:
            ct_str = _safe(row, ct_idx)
            if not ct_str:
                skipped_empty += 1
                continue
            try:
                ct = _as_utc(datetime.fromisoformat(ct_str))
            except ValueError:
                logger.warning("Cannot parse created_time %r in sheet '%s'", ct_str, sheet["name"])
                skipped_parse += 1
                continue
            if ct > last_dt:
                all_new.append((ct, row, header, sheet))
            else:
                skipped_old += 1
        logger.info(
            "Sheet '%s': skipped empty=%d parse_err=%d too_old=%d new=%d last_dt=%s",
            sheet["name"], skipped_empty, skipped_parse, skipped_old,
            len([x for x in all_new if x[3]["name"] == sheet["name"]]),
            last_dt.isoformat(),
        )

    if not all_new:
        return 0

    all_new.sort(key=lambda x: x[0])
    hr_list = config.HR_LIST
    processed = 0

    for ct, row, header, sheet in all_new:
        hr_name, tg_username = hr_list[rr_counter % len(hr_list)]

        cols = sheet["cols"]
        source = sheet["source"]

        def g(key: str) -> str:
            return _get(row, header, cols, key)

        full_name = g("full_name")
        telegram = g("telegram")
        phone = g("phone")
        platform = g("platform")
        age = g("age")

        tg_display = _normalize_tg(telegram, full_name)

        if sheet["type"] in ("yd", "yd_geo"):
            if sheet["type"] == "yd_geo":
                source = g("adset_name") or sheet["source"]
            text = (
                f"{html.escape(source)}\n"
                f"└ <b>{html.escape(hr_name)}</b> | {html.escape(tg_username)}\n"
                f"\n"
                f"From: <b>{html.escape(platform)}</b>\n"
                f"Age: <b>{html.escape(age)}</b>\n"
                f"EXP: <b>{html.escape(g('experience'))}</b>\n"
                f"EN: <b>{html.escape(g('english'))}</b>\n"
                f"PC: <b>{html.escape(g('pc'))}</b>\n"
                f"\n"
                f"👤 {html.escape(tg_display)} | <b>{html.escape(full_name)}</b>\n"
                f"📞 {html.escape(phone)}"
            )
        else:  # belgrade
            text = (
                f"{html.escape(source)}\n"
                f"└ <b>{html.escape(hr_name)}</b> | {html.escape(tg_username)}\n"
                f"\n"
                f"From: <b>{html.escape(platform)}</b>\n"
                f"Age: <b>{html.escape(age)}</b>\n"
                f"City: <b>{html.escape(g('city'))}</b>\n"
                f"EN LVL: <b>{html.escape(g('english'))}</b>\n"
                f"Office: <b>{html.escape(g('office'))}</b>\n"
                f"Night shifts: <b>{html.escape(g('night_shifts'))}</b>\n"
                f"\n"
                f"👤 {html.escape(tg_display)} | <b>{html.escape(full_name)}</b>\n"
                f"📞 {html.escape(phone)}"
            )

        written = await append_lego_lead({
            "Стейдж HR, точно так,как в CRM": hr_name,
            "Дата": ct.strftime("%d.%m.%Y"),
            "Имя Лида": full_name,
            "Telegram": tg_display,
            "Телефон": phone,
            "Должность": "manager",
            "Источник": source,
        })
        if not written:
            await set_lego_state({
                "last_processed_created_time": ct.isoformat(),
                "rr_counter": rr_counter,
            })
            continue

        rr_counter += 1
        for attempt in range(3):
            try:
                await bot.send_message(chat_id=config.GROUP_CHAT_ID, text=text, parse_mode="HTML")
                break
            except RetryAfter as e:
                logger.warning("Flood control: waiting %ds (attempt %d/3)", e.retry_after, attempt + 1)
                await asyncio.sleep(e.retry_after + 1)
        await asyncio.sleep(2)
        processed += 1
        await set_lego_state({
            "last_processed_created_time": ct.isoformat(),
            "rr_counter": rr_counter,
        })

    logger.info("lego import: processed %d rows", processed)
    return processed
