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


def _append_row_sync(data: dict) -> int:
    _refresh_creds()
    result = _service.spreadsheets().values().append(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        range=f"{_SHEET}!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [[""]]},
    ).execute()
    updated_range = result.get("updates", {}).get("updatedRange", "")
    match = re.search(r"(\d+)$", updated_range)
    row_number = int(match.group(1)) if match else 0

    if not row_number:
        logger.error("Could not parse row number from: %s", updated_range)
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
        _service.spreadsheets().values().batchUpdate(
            spreadsheetId=config.GOOGLE_SHEETS_ID,
            body={"valueInputOption": "RAW", "data": batch_data},
        ).execute()

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
    _service.spreadsheets().values().batchUpdate(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        body={"valueInputOption": "RAW", "data": batch_data},
    ).execute()


async def update_date_svyazi(row_number: int, now: datetime) -> None:
    await asyncio.to_thread(_update_date_svyazi_sync, row_number, now)


async def append_lead(crm_name: str, lead_user, message_text: str) -> int:
    now = datetime.now(timezone.utc)
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
