import asyncio
import logging
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
    return header


_header = _read_header()


def _append_row_sync(data: dict) -> None:
    if _creds.expired and hasattr(_creds, "refresh"):
        _creds.refresh(google.auth.transport.requests.Request())
    row = [data.get(col, "") for col in _header]
    _service.spreadsheets().values().append(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        range=f"{_SHEET}!A:Z",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


async def append_lead(crm_name: str, lead_user, message_text: str) -> None:
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
        "Дата связи": dt,
    }
    await asyncio.to_thread(_append_row_sync, data)
