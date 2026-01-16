from contextlib import asynccontextmanager
import csv
import io
import json
from typing import Dict, List

import crud
from fastapi import Body, FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from models import CodeEntry
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError, WriteError

MONGO_URL = "mongodb://root:example@mongo:27017"
DB_NAME = "appdb"


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


@app.get("/entries/export-csv")
async def export_all_entries_csv():
    """Export all entries as CSV."""
    cursor = app.mongodb["code_entries"].find({}).sort("_id", 1)
    docs = await cursor.to_list(length=None)

    if not docs:
        return StreamingResponse(
            iter(["No entries found"]),
            media_type="text/csv"
        )

    # Create CSV in memory
    output = io.StringIO()
    fieldnames = [
        "id", "code_hash", "repo_url", "commit_hash", "commit_date",
        "ingest_timestamp", "cppcheck_labels",
        "memory_management", "invalid_access", "uninitialized",
        "concurrency", "logic_error", "resource_leak",
        "security_portability", "code_quality_performance",
        "code_original", "code_fixed"
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for doc in docs:
        entry = CodeEntry(**doc)
        labels = entry.labels
        groups = labels.groups if labels else None

        row = {
            "id": str(entry.id) if entry.id else "",
            "code_hash": entry.code_hash,
            "repo_url": entry.repo.url if entry.repo else "",
            "commit_hash": entry.repo.commit_hash if entry.repo else "",
            "commit_date": entry.repo.commit_date.isoformat() if entry.repo and entry.repo.commit_date else "",
            "ingest_timestamp": entry.ingest_timestamp.isoformat() if entry.ingest_timestamp else "",
            "cppcheck_labels": "|".join(labels.cppcheck) if labels else "",
            "memory_management": groups.memory_management if groups else False,
            "invalid_access": groups.invalid_access if groups else False,
            "uninitialized": groups.uninitialized if groups else False,
            "concurrency": groups.concurrency if groups else False,
            "logic_error": groups.logic_error if groups else False,
            "resource_leak": groups.resource_leak if groups else False,
            "security_portability": groups.security_portability if groups else False,
            "code_quality_performance": groups.code_quality_performance if groups else False,
            "code_original": entry.code_original.replace("\n", "\\n") if entry.code_original else "",
            "code_fixed": entry.code_fixed.replace("\n", "\\n") if entry.code_fixed else "",
        }
        writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=entries.csv"}
    )


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


@app.post("/entries/query/", response_model=List[CodeEntry])
async def query_entries(filter: Dict = Body(default={}), sort: Dict = Body(default={}), limit: int = 100):
    return await crud.list_entries(app.mongodb, filter, sort, limit)


@app.post("/entries/{entry_id}/labels/add")
async def add_label(entry_id: str, label: str = Body(..., embed=True)):
    """Add a label to an entry's cppcheck labels."""
    count = await crud.add_label(app.mongodb, entry_id, label)
    if count == 0:
        raise HTTPException(status_code=404, detail="Entry not found or label already exists")
    return {"updated": count, "label": label, "action": "added"}


@app.post("/entries/{entry_id}/labels/remove")
async def remove_label(entry_id: str, label: str = Body(..., embed=True)):
    """Remove a label from an entry's cppcheck labels."""
    count = await crud.remove_label(app.mongodb, entry_id, label)
    if count == 0:
        raise HTTPException(status_code=404, detail="Entry not found or label does not exist")
    return {"updated": count, "label": label, "action": "removed"}


@app.post("/entries/{entry_id}/labels/group")
async def set_label_group(
    entry_id: str,
    group: str = Body(...),
    value: bool = Body(...)
):
    """Set a label group boolean value."""
    count = await crud.set_label_group(app.mongodb, entry_id, group, value)
    if count == 0:
        raise HTTPException(status_code=404, detail="Entry not found or invalid group")
    return {"updated": count, "group": group, "value": value}


@app.get("/labels/all")
async def get_all_labels():
    """Get all unique cppcheck labels in the database."""
    labels = await crud.get_all_labels(app.mongodb)
    return {"labels": labels, "count": len(labels)}


@app.get("/stats/")
async def get_stats():
    """Get database statistics."""
    total = await crud.get_entry_count(app.mongodb)

    # Count by label groups
    group_counts = {}
    groups = [
        "memory_management", "invalid_access", "uninitialized",
        "concurrency", "logic_error", "resource_leak",
        "security_portability", "code_quality_performance"
    ]

    for group in groups:
        count = await crud.get_entry_count(
            app.mongodb,
            {f"labels.groups.{group}": True}
        )
        group_counts[group] = count

    return {
        "total_entries": total,
        "by_group": group_counts
    }

