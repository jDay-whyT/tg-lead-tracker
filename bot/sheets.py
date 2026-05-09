import asyncio
from datetime import datetime, timezone

import google.auth
import google.auth.transport.requests
from googleapiclient.discovery import build

import config

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_creds, _ = google.auth.default(scopes=_SCOPES)
_service = build("sheets", "v4", credentials=_creds)


def _append_row_sync(row: list) -> None:
    if _creds.expired and hasattr(_creds, "refresh"):
        _creds.refresh(google.auth.transport.requests.Request())
    _service.spreadsheets().values().append(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        range="Leads!A:G",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


async def append_lead(manager_username: str, lead_user, message_text: str) -> None:
    now = datetime.now(timezone.utc)
    row = [
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M:%S"),
        manager_username or "",
        getattr(lead_user, "username", "") or "",
        f"{getattr(lead_user, 'first_name', '') or ''} {getattr(lead_user, 'last_name', '') or ''}".strip(),
        str(lead_user.id),
        (message_text or "")[:200],
    ]
    await asyncio.to_thread(_append_row_sync, row)
