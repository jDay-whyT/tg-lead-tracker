import asyncio
import logging
import ssl
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import google.auth
import google.auth.transport.requests
from googleapiclient.discovery import build

import config

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_creds, _ = google.auth.default(scopes=_SCOPES)
_service = None


def _build_service():
    global _service
    _creds.refresh(google.auth.transport.requests.Request())
    _service = build("sheets", "v4", credentials=_creds)


_build_service()


def _execute(make_req, retries: int = 3):
    """Call make_req().execute() with retry on stale-connection errors."""
    for attempt in range(retries):
        try:
            return make_req().execute()
        except (BrokenPipeError, ssl.SSLError, OSError) as exc:
            if attempt == retries - 1:
                raise
            logger.warning("Sheets API connection error (attempt %d/%d): %s — rebuilding service", attempt + 1, retries, exc)
            time.sleep(0.5 * (attempt + 1))
            _build_service()


_SHEET = "candidates"


def _read_header() -> list[str]:
    result = _execute(lambda: _service.spreadsheets().values().get(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        range=f"{_SHEET}!1:1",
    ))
    rows = result.get("values", [])
    header = rows[0] if rows else []
    if not header:
        logger.warning("%s sheet has no header row — writes will be empty", _SHEET)
    else:
        logger.info("Header read from %s: %s", _SHEET, header)
    return header


_header: list[str] = []
_date_svyazi_col: str = ""
_time_svyazi_col: str = ""


def _col_letter(n: int) -> str:
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def init_header() -> None:
    global _header, _date_svyazi_col, _time_svyazi_col
    _header = _read_header()
    _date_svyazi_col = (
        _col_letter(_header.index("Дата связи") + 1) if "Дата связи" in _header else ""
    )
    _time_svyazi_col = (
        _col_letter(_header.index("Время связи") + 1) if "Время связи" in _header else ""
    )


def _refresh_creds() -> None:
    if _creds.expired and hasattr(_creds, "refresh"):
        _creds.refresh(google.auth.transport.requests.Request())


_CRM_COL_NAME = "Стейдж HR, точно так,как в CRM"


def _telegram_exists(value: str) -> bool:
    if "Telegram" not in _header:
        return False
    col = _col_letter(_header.index("Telegram") + 1)
    result = _execute(lambda: _service.spreadsheets().values().get(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        range=f"{_SHEET}!{col}2:{col}10000",
    ))
    values = result.get("values", [])
    return any(row and row[0] == value for row in values)


def _find_first_empty_row() -> int:
    if _CRM_COL_NAME not in _header:
        logger.error("Column '%s' not in header — cannot find empty row", _CRM_COL_NAME)
        return 0
    col = _col_letter(_header.index(_CRM_COL_NAME) + 1)
    result = _execute(lambda: _service.spreadsheets().values().get(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        range=f"{_SHEET}!{col}2:{col}10000",
    ))
    values = result.get("values", [])
    for i, row in enumerate(values):
        if not row or not str(row[0]).strip():
            return i + 2
    return len(values) + 2


def _append_row_sync(data: dict) -> int:
    _refresh_creds()
    telegram_value = data.get("Telegram", "")
    if telegram_value and _telegram_exists(telegram_value):
        logger.info("Duplicate in Sheets: skipped (%s)", telegram_value)
        return 0
    row_number = _find_first_empty_row()
    if not row_number:
        return 0

    batch_data = []
    for col_name, value in data.items():
        if col_name in _header:
            col_letter = _col_letter(_header.index(col_name) + 1)
            batch_data.append({
                "range": f"{_SHEET}!{col_letter}{row_number}",
                "values": [[value]],
            })

    if batch_data:
        logger.info("Writing row %s: %s", row_number, {k: v for k, v in data.items() if k in _header})
        _execute(lambda: _service.spreadsheets().values().batchUpdate(
            spreadsheetId=config.GOOGLE_SHEETS_ID,
            body={"valueInputOption": "RAW", "data": batch_data},
        ))

    return row_number


def _update_date_svyazi_sync(row_number: int, now: datetime) -> None:
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")
    batch_data = []
    if _date_svyazi_col:
        batch_data.append({
            "range": f"{_SHEET}!{_date_svyazi_col}{row_number}",
            "values": [[date_str]],
        })
    else:
        logger.warning("Дата связи column not found in header — skipping")
    if _time_svyazi_col:
        batch_data.append({
            "range": f"{_SHEET}!{_time_svyazi_col}{row_number}",
            "values": [[time_str]],
        })
    else:
        logger.warning("Время связи column not found in header — skipping")
    if not batch_data:
        return
    _refresh_creds()
    _execute(lambda: _service.spreadsheets().values().batchUpdate(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        body={"valueInputOption": "RAW", "data": batch_data},
    ))


async def update_date_svyazi(row_number: int, now: datetime) -> None:
    await asyncio.to_thread(_update_date_svyazi_sync, row_number, now)


async def append_lead(crm_name: str, lead_user, message_text: str) -> int:
    now = datetime.now(ZoneInfo("Europe/Kiev"))
    first = getattr(lead_user, "first_name", "") or ""
    last = getattr(lead_user, "last_name", "") or ""
    full_name = f"{first} {last}".strip()
    username = getattr(lead_user, "username", "") or ""
    data = {
        "Стейдж HR, точно так,как в CRM": crm_name or "",
        "Дата": now.strftime("%d.%m.%Y"),
        "Время": now.strftime("%H:%M"),
        "Telegram": f"@{username}" if username else full_name,
        "Должность": "manager",
    }
    return await asyncio.to_thread(_append_row_sync, data)
