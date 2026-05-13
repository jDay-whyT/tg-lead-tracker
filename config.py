import os

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
ADMIN_CHAT_IDS: list[int] = [int(x) for x in os.environ["ADMIN_CHAT_ID"].split(",") if x.strip()]
GOOGLE_SHEETS_ID: str = os.environ["GOOGLE_SHEETS_ID"]
FIRESTORE_PROJECT_ID: str = os.environ["FIRESTORE_PROJECT_ID"]
WEBHOOK_SECRET: str = os.environ.get("WEBHOOK_SECRET", "")
LEGO_FORM_ID: str = os.environ.get("LEGO_FORM_ID", "")
HR_LIST: list[tuple[str, str]] = [
    (pair[0].strip(), pair[1].strip())
    for entry in os.environ.get("HR_LIST", "").split(",")
    if ":" in entry
    for pair in [entry.split(":", 1)]
]
GROUP_CHAT_ID: int = int(os.environ.get("GROUP_CHAT_ID", "0"))
