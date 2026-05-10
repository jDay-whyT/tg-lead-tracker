import asyncio
import logging
import re
from datetime import datetime, timezone

import google.auth
import google.auth.transport.requests
from googleapiclient.discovery import build

import config

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_creds, _ = google.auth.default(scopes=_SCOPES)
_service = build("sheets", "v4", credentials=_creds)


_SHEET = "candidates"


def _read_header() -> list[str]:
    result = _service.spreadsheets().values().get(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        range=f"{_SHEET}!1:1",
    ).execute()
    rows = result.get("values", [])
    header = rows[0] if rows else []
    if not header:
        logger.warning("%s sheet has no header row — writes will be empty", _SHEET)
    else:
        logger.info("Header read from %s: %s", _SHEET, header)
    return header


_header: list[str] = []
_date_svyazi_col: str = ""


def _col_letter(n: int) -> str:
    result = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def init_header() -> None:
    global _header, _date_svyazi_col
    _header = _read_header()
    _date_svyazi_col = (
        _col_letter(_header.index("Дата связи") + 1) if "Дата связи" in _header else ""
    )


def _append_row_sync(data: dict) -> int:
    if _creds.expired and hasattr(_creds, "refresh"):
        _creds.refresh(google.auth.transport.requests.Request())
    row = [data.get(col, "") for col in _header]
    logger.info("Writing row — header: %s | data keys: %s | row: %s", _header, list(data.keys()), row)
    result = _service.spreadsheets().values().append(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        range=f"{_SHEET}!A:Z",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
    updated_range = result.get("updates", {}).get("updatedRange", "")
    match = re.search(r"(\d+)$", updated_range)
    return int(match.group(1)) if match else 0


def _update_date_svyazi_sync(row_number: int, dt_str: str) -> None:
    if not _date_svyazi_col:
        logger.warning("Дата связи column not found in header — skipping update")
        return
    if _creds.expired and hasattr(_creds, "refresh"):
        _creds.refresh(google.auth.transport.requests.Request())
    _service.spreadsheets().values().update(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        range=f"{_SHEET}!{_date_svyazi_col}{row_number}",
        valueInputOption="RAW",
        body={"values": [[dt_str]]},
    ).execute()


async def update_date_svyazi(row_number: int, dt_str: str) -> None:
    await asyncio.to_thread(_update_date_svyazi_sync, row_number, dt_str)


async def append_lead(crm_name: str, lead_user, message_text: str) -> int:
    now = datetime.now(timezone.utc)
    dt = now.strftime("%d.%m.%y %H:%M")
    first = getattr(lead_user, "first_name", "") or ""
    last = getattr(lead_user, "last_name", "") or ""
    full_name = f"{first} {last}".strip()
    username = getattr(lead_user, "username", "") or ""
    data = {
        "Стейдж HR, точно так,как в CRM": crm_name or "",
        "Дата": dt,
        "Telegram": f"@{username}" if username else full_name,
        "Должность": "manager",
    }
    return await asyncio.to_thread(_append_row_sync, data)
