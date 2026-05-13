import os

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
ADMIN_CHAT_IDS: list[int] = [int(x) for x in os.environ["ADMIN_CHAT_ID"].split(",") if x.strip()]
GOOGLE_SHEETS_ID: str = os.environ["GOOGLE_SHEETS_ID"]
FIRESTORE_PROJECT_ID: str = os.environ["FIRESTORE_PROJECT_ID"]
WEBHOOK_SECRET: str = os.environ.get("WEBHOOK_SECRET", "")
LEGO_FORM_ID: str = os.environ.get("LEGO_FORM_ID", "")
HR_CRM_NAMES: list[str] = [x.strip() for x in os.environ.get("HR_CRM_NAMES", "").split(",") if x.strip()]
GROUP_CHAT_ID: int = int(os.environ.get("GROUP_CHAT_ID", "0"))
