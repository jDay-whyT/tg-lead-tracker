import config
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

_db = firestore.AsyncClient(project=config.FIRESTORE_PROJECT_ID)

MANAGERS = "managers"
LEADS = "leads"


async def save_manager(connection_id: str, data: dict) -> None:
    await _db.collection(MANAGERS).document(connection_id).set(data)


async def get_manager(connection_id: str) -> dict | None:
    doc = await _db.collection(MANAGERS).document(connection_id).get()
    return doc.to_dict() if doc.exists else None


async def update_manager_status(connection_id: str, status: str) -> None:
    await _db.collection(MANAGERS).document(connection_id).update({"status": status})


async def delete_manager_by_username(username: str) -> bool:
    query = _db.collection(MANAGERS).where(filter=FieldFilter("username", "==", username)).limit(1)
    async for doc in query.stream():
        await doc.reference.delete()
        return True
    return False


async def get_manager_by_user_id(user_id: int) -> tuple[str, dict] | None:
    query = _db.collection(MANAGERS).where(filter=FieldFilter("user_id", "==", user_id)).limit(1)
    async for doc in query.stream():
        d = doc.to_dict()
        d["connection_id"] = doc.id
        return doc.id, d
    return None


async def reset_manager_crm(connection_id: str) -> None:
    await _db.collection(MANAGERS).document(connection_id).update({
        "status": "awaiting_crm_name",
        "crm_name": "",
    })


async def update_manager_crm(connection_id: str, crm_name: str) -> None:
    await _db.collection(MANAGERS).document(connection_id).update({
        "crm_name": crm_name,
        "status": "pending",
    })


async def lead_exists(connection_id: str, lead_user_id: int) -> bool:
    doc_id = f"{connection_id}_{lead_user_id}"
    doc = await _db.collection(LEADS).document(doc_id).get()
    return doc.exists


async def get_lead(connection_id: str, lead_user_id: int) -> dict | None:
    doc_id = f"{connection_id}_{lead_user_id}"
    doc = await _db.collection(LEADS).document(doc_id).get()
    return doc.to_dict() if doc.exists else None


async def mark_lead_seen(connection_id: str, lead_user_id: int, row_number: int) -> None:
    doc_id = f"{connection_id}_{lead_user_id}"
    await _db.collection(LEADS).document(doc_id).set({
        "connection_id": connection_id,
        "lead_user_id": lead_user_id,
        "row_number": row_number,
        "replied": False,
    })


async def mark_lead_replied(connection_id: str, lead_user_id: int) -> None:
    doc_id = f"{connection_id}_{lead_user_id}"
    await _db.collection(LEADS).document(doc_id).update({"replied": True})


async def list_managers() -> list[dict]:
    result = []
    async for doc in _db.collection(MANAGERS).stream():
        d = doc.to_dict()
        d["connection_id"] = doc.id
        result.append(d)
    return result


LEGO_STATE = "lego_state"


async def get_lego_state() -> dict | None:
    doc = await _db.collection(LEGO_STATE).document("state").get()
    return doc.to_dict() if doc.exists else None


async def set_lego_state(data: dict) -> None:
    await _db.collection(LEGO_STATE).document("state").set(data)
