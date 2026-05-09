import asyncio
from datetime import datetime, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build

import config

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _append_row_sync(row: list) -> None:
    creds = service_account.Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_PATH, scopes=_SCOPES
    )
    service = build("sheets", "v4", credentials=creds)
    service.spreadsheets().values().append(
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
