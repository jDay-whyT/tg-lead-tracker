import os
from unittest.mock import MagicMock, patch

# Set env vars before any project module is imported
os.environ.setdefault("BOT_TOKEN", "0:test")
os.environ.setdefault("ADMIN_CHAT_ID", "1")
os.environ.setdefault("GOOGLE_SHEETS_ID", "test_sheet")
os.environ.setdefault("FIRESTORE_PROJECT_ID", "test_project")
os.environ.setdefault("WEBHOOK_SECRET", "")
os.environ.setdefault("LEGO_FORM_ID", "test_lego_form")
os.environ.setdefault("HR_LIST", "Mia:@mia_adsassist,Dima:@dimHRk")
os.environ.setdefault("GROUP_CHAT_ID", "-100500")

# Patch Google auth and Sheets API before sheets.py module-level code runs
_mock_creds = MagicMock()
_mock_creds.expired = False
_mock_creds.token = "fake-token"

patch("google.auth.default", return_value=(_mock_creds, "test-project")).start()
patch("gspread.Client", return_value=MagicMock()).start()
