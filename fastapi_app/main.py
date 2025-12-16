from contextlib import asynccontextmanager
from typing import Dict, List

import crud
from fastapi import Body, FastAPI, HTTPException
from models import CodeEntry
from motor.motor_asyncio import AsyncIOMotorClient

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
    entry_id = await crud.create_entry(app.mongodb, entry)
    return {"id": entry_id}


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
