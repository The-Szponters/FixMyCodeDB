from motor.motor_asyncio import AsyncIOMotorClient
from models import CodeEntry
from typing import Dict
from bson import ObjectId

# Connect to MongoDB
client = AsyncIOMotorClient("mongodb://root:example@mongo:27017")
db = client.appdb
collection = db.code_entries


# Create a new entry
async def create_entry(entry: CodeEntry):
    doc = entry.dict()
    result = await collection.insert_one(doc)
    return str(result.inserted_id)


# Read an entry by ID
async def get_entry(entry_id: str):
    return await collection.find_one({"_id": ObjectId(entry_id)})


# Update an entry by ID
async def update_entry(entry_id: str, data: Dict):
    result = await collection.update_one({"_id": ObjectId(entry_id)}, {"$set": data})
    return result.modified_count


# Delete an entry by ID
async def delete_entry(entry_id: str):
    result = await collection.delete_one({"_id": ObjectId(entry_id)})
    return result.deleted_count


# List all entries with optional filtering, sorting, and limit
async def list_entries(filter_dict: Dict = {}, sort_dict: Dict = {}, limit: int = 100):
    # Convert _id from string to ObjectId if present
    if "_id" in filter_dict:
        try:
            filter_dict["_id"] = ObjectId(filter_dict["_id"])
        except Exception:
            # If invalid ObjectId string
            return []

    cursor = collection.find(filter_dict)
    if sort_dict:
        sort_list = [(k, v) for k, v in sort_dict.items()]
        cursor = cursor.sort(sort_list)
    return await cursor.to_list(length=limit)
