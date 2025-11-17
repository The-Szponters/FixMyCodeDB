from fastapi import FastAPI, HTTPException
from models import CodeEntry
from crud import create_entry, get_entry, update_entry, delete_entry, list_entries
from typing import Optional, Dict
from fastapi.responses import JSONResponse

app = FastAPI(title="FixMyCode API")


# Helper to serialize ObjectId to str
def serialize_doc(doc):
    doc["_id"] = str(doc["_id"])
    return doc


# Create
@app.post("/entries/")
async def create(code: CodeEntry):
    entry_id = await create_entry(code)
    return {"id": entry_id}


# Read by ID
@app.get("/entries/{entry_id}")
async def read(entry_id: str):
    entry = await get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return serialize_doc(entry)


# Read all
@app.get("/entries/", response_class=JSONResponse)
async def get_all_entries():
    docs = await list_entries()
    return [serialize_doc(doc) for doc in docs]


# Update by ID
@app.put("/entries/{entry_id}")
async def update(entry_id: str, data: Dict):
    count = await update_entry(entry_id, data)
    if count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"updated": count}


# Delete by ID
@app.delete("/entries/{entry_id}")
async def delete(entry_id: str):
    count = await delete_entry(entry_id)
    if count == 0:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"deleted": count}


# Advanced filtering + sorting
@app.post("/entries/query/")
async def query_entries(
    filter: Optional[Dict] = {},
    sort: Optional[Dict] = {},
    limit: int = 100
):
    """
    filter: dict of field:value, e.g. {"labels.groups.memory_errors":1}
    sort: dict of field:direction, direction=1 for asc, -1 for desc
    limit: maximum number of entries to return
    """
    entries = await list_entries(filter, sort, limit)
    return [serialize_doc(e) for e in entries]
