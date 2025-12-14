from typing import Dict, List, Optional

from bson import ObjectId
from models import CodeEntry
from motor.motor_asyncio import AsyncIOMotorDatabase

COLL = "code_entries"


async def create_entry(db: AsyncIOMotorDatabase, entry: CodeEntry) -> str:
    doc = entry.model_dump(by_alias=True, exclude=["id"])
    result = await db[COLL].insert_one(doc)
    return str(result.inserted_id)


async def get_entry(db: AsyncIOMotorDatabase, entry_id: str) -> Optional[CodeEntry]:
    try:
        oid = ObjectId(entry_id)
    except Exception:
        return None

    doc = await db[COLL].find_one({"_id": oid})
    if doc:
        return CodeEntry(**doc)
    return None


async def update_entry(db: AsyncIOMotorDatabase, entry_id: str, data: Dict) -> int:
    try:
        oid = ObjectId(entry_id)
    except Exception:
        return 0

    result = await db[COLL].update_one({"_id": oid}, {"$set": data})
    return result.modified_count


async def delete_entry(db: AsyncIOMotorDatabase, entry_id: str) -> int:
    try:
        oid = ObjectId(entry_id)
    except Exception:
        return 0

    result = await db[COLL].delete_one({"_id": oid})
    return result.deleted_count


async def list_entries(db: AsyncIOMotorDatabase, filter_dict: Dict = {}, sort_dict: Dict = {}, limit: int = 100) -> List[CodeEntry]:

    if "_id" in filter_dict and isinstance(filter_dict["_id"], str):
        try:
            filter_dict["_id"] = ObjectId(filter_dict["_id"])
        except Exception:
            return []

    cursor = db[COLL].find(filter_dict)

    if sort_dict:
        sort_list = [(k, v) for k, v in sort_dict.items()]
        cursor = cursor.sort(sort_list)

    docs = await cursor.to_list(length=limit)
    return [CodeEntry(**doc) for doc in docs]
