import config
from google.cloud import firestore
from google.oauth2 import service_account

_creds = service_account.Credentials.from_service_account_file(config.GOOGLE_CREDENTIALS_PATH)
_db = firestore.AsyncClient(project=config.FIRESTORE_PROJECT_ID, credentials=_creds)

MANAGERS = "managers"


async def save_manager(connection_id: str, data: dict) -> None:
    await _db.collection(MANAGERS).document(connection_id).set(data)


async def get_manager(connection_id: str) -> dict | None:
    doc = await _db.collection(MANAGERS).document(connection_id).get()
    return doc.to_dict() if doc.exists else None


async def update_manager_status(connection_id: str, status: str) -> None:
    await _db.collection(MANAGERS).document(connection_id).update({"status": status})


async def list_managers() -> list[dict]:
    result = []
    async for doc in _db.collection(MANAGERS).stream():
        d = doc.to_dict()
        d["connection_id"] = doc.id
        result.append(d)
    return result
