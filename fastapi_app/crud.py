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


async def add_label(db: AsyncIOMotorDatabase, entry_id: str, label: str) -> int:
    """
    Add a label to an entry's cppcheck labels list.

    Args:
        db: Database connection
        entry_id: Entry ID
        label: Label to add

    Returns:
        Number of modified documents (0 or 1)
    """
    try:
        oid = ObjectId(entry_id)
    except Exception:
        return 0

    result = await db[COLL].update_one(
        {"_id": oid},
        {"$addToSet": {"labels.cppcheck": label}}
    )
    return result.modified_count


async def remove_label(db: AsyncIOMotorDatabase, entry_id: str, label: str) -> int:
    """
    Remove a label from an entry's cppcheck labels list.

    Args:
        db: Database connection
        entry_id: Entry ID
        label: Label to remove

    Returns:
        Number of modified documents (0 or 1)
    """
    try:
        oid = ObjectId(entry_id)
    except Exception:
        return 0

    result = await db[COLL].update_one(
        {"_id": oid},
        {"$pull": {"labels.cppcheck": label}}
    )
    return result.modified_count


async def set_label_group(
    db: AsyncIOMotorDatabase,
    entry_id: str,
    group: str,
    value: bool
) -> int:
    """
    Set a label group boolean value.

    Args:
        db: Database connection
        entry_id: Entry ID
        group: Label group name (e.g., 'memory_management')
        value: Boolean value to set

    Returns:
        Number of modified documents (0 or 1)
    """
    valid_groups = [
        "memory_management",
        "invalid_access",
        "uninitialized",
        "concurrency",
        "logic_error",
        "resource_leak",
        "security_portability",
        "code_quality_performance",
    ]

    if group not in valid_groups:
        return 0

    try:
        oid = ObjectId(entry_id)
    except Exception:
        return 0

    result = await db[COLL].update_one(
        {"_id": oid},
        {"$set": {f"labels.groups.{group}": value}}
    )
    return result.modified_count


async def get_entry_count(db: AsyncIOMotorDatabase, filter_dict: Dict = {}) -> int:
    """
    Get count of entries matching a filter.

    Args:
        db: Database connection
        filter_dict: MongoDB filter dictionary

    Returns:
        Count of matching entries
    """
    return await db[COLL].count_documents(filter_dict)


async def get_all_labels(db: AsyncIOMotorDatabase) -> List[str]:
    """
    Get all unique cppcheck labels in the database.

    Args:
        db: Database connection

    Returns:
        List of unique label strings
    """
    pipeline = [
        {"$unwind": "$labels.cppcheck"},
        {"$group": {"_id": "$labels.cppcheck"}},
        {"$sort": {"_id": 1}}
    ]
    cursor = db[COLL].aggregate(pipeline)
    results = await cursor.to_list(length=None)
    return [r["_id"] for r in results]

