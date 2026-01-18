from contextlib import asynccontextmanager
import json
from typing import Dict, List

import crud
from fastapi import Body, FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from models import CodeEntry, LabelUpdateRequest
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, WriteError

MONGO_URL = "mongodb://root:example@mongo:27017"
DB_NAME = "appdb"

# ============================================================================
# Label Mapping: CLI label names -> labels.groups field names
# ============================================================================
LABEL_TO_GROUP_FIELD = {
    # User-friendly aliases
    "MemError": "memory_management",
    "MemoryManagement": "memory_management",
    "InvalidAccess": "invalid_access",
    "Uninitialized": "uninitialized",
    "Concurrency": "concurrency",
    "LogicError": "logic_error",
    "ResourceLeak": "resource_leak",
    "SecurityPortability": "security_portability",
    "CodeQualityPerformance": "code_quality_performance",
    # Direct field names (also accepted)
    "memory_management": "memory_management",
    "invalid_access": "invalid_access",
    "uninitialized": "uninitialized",
    "concurrency": "concurrency",
    "logic_error": "logic_error",
    "resource_leak": "resource_leak",
    "security_portability": "security_portability",
    "code_quality_performance": "code_quality_performance",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.mongodb_client = AsyncIOMotorClient(MONGO_URL)
    app.mongodb = app.mongodb_client[DB_NAME]
    print("Connected to MongoDB")
    yield
    app.mongodb_client.close()
    print("Disconnected from MongoDB")


app = FastAPI(title="FixMyCode API", lifespan=lifespan)


@app.post("/entries/", response_model=Dict[str, str], status_code=201)
async def create(entry: CodeEntry):
    try:
        entry_id = await crud.create_entry(app.mongodb, entry)
        return {"id": entry_id}
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Duplicate entry (code_hash already exists)")
    except WriteError as e:
        raise HTTPException(status_code=422, detail=f"MongoDB write failed: {e}")


@app.get("/entries/export-all")
async def export_all_entries():
    cursor = app.mongodb["code_entries"].find({}).sort("_id", 1)

    async def generate():
        async for doc in cursor:
            entry = CodeEntry(**doc)
            payload = jsonable_encoder(entry, by_alias=True)
            yield json.dumps(payload, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.get("/entries/{entry_id}", response_model=CodeEntry)
async def read(entry_id: str):
    entry = await crud.get_entry(app.mongodb, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@app.get("/entries/", response_model=List[CodeEntry])
async def get_all_entries(limit: int = 100):
    return await crud.list_entries(app.mongodb, limit=limit)


@app.put("/entries/{entry_id}")
async def update(entry_id: str, data: Dict = Body(...)):
    count = await crud.update_entry(app.mongodb, entry_id, data)
    if count == 0:
        raise HTTPException(status_code=404, detail="Entry not found or no changes made")
    return {"updated": count}


@app.delete("/entries/{entry_id}")
async def delete(entry_id: str):
    count = await crud.delete_entry(app.mongodb, entry_id)
    if count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"deleted": count}


@app.patch("/entries/{entry_id}/labels", response_model=CodeEntry)
async def update_labels(entry_id: str, request: LabelUpdateRequest):
    """
    Add or remove labels from an entry.

    Labels can be:
    - Group labels: MemError, LogicError, Concurrency, etc. (mapped to labels.groups.*)
    - Cppcheck labels: Any other string (added to labels.cppcheck array)

    Body:
    {
        "add": ["MemError", "customLabel"],
        "remove": ["LogicError"]
    }
    """
    # First, verify the entry exists
    entry = await crud.get_entry(app.mongodb, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    # Build the update operation
    update_ops = {}
    cppcheck_add = []
    cppcheck_remove = []

    # Process labels to add
    for label in request.add:
        if label in LABEL_TO_GROUP_FIELD:
            field_name = LABEL_TO_GROUP_FIELD[label]
            update_ops[f"labels.groups.{field_name}"] = True
        else:
            # Treat as cppcheck label
            cppcheck_add.append(label)

    # Process labels to remove
    for label in request.remove:
        if label in LABEL_TO_GROUP_FIELD:
            field_name = LABEL_TO_GROUP_FIELD[label]
            update_ops[f"labels.groups.{field_name}"] = False
        else:
            # Treat as cppcheck label
            cppcheck_remove.append(label)

    # Apply group updates
    if update_ops:
        await crud.update_entry(app.mongodb, entry_id, update_ops)

    # Apply cppcheck array updates
    if cppcheck_add:
        await crud.add_to_cppcheck_labels(app.mongodb, entry_id, cppcheck_add)

    if cppcheck_remove:
        await crud.remove_from_cppcheck_labels(app.mongodb, entry_id, cppcheck_remove)

    # Return the updated entry
    updated_entry = await crud.get_entry(app.mongodb, entry_id)
    return updated_entry


@app.post("/entries/query/", response_model=List[CodeEntry])
async def query_entries(filter: Dict = Body(default={}), sort: Dict = Body(default={}), limit: int = 100):
    return await crud.list_entries(app.mongodb, filter, sort, limit)
