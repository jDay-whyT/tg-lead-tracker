import os

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID: int = int(os.environ["ADMIN_CHAT_ID"])
GOOGLE_SHEETS_ID: str = os.environ["GOOGLE_SHEETS_ID"]
FIRESTORE_PROJECT_ID: str = os.environ["FIRESTORE_PROJECT_ID"]
WEBHOOK_SECRET: str = os.environ.get("WEBHOOK_SECRET", "")

GOOGLE_CREDENTIALS_PATH: str = os.environ["GOOGLE_CREDENTIALS_PATH"]
