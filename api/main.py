from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api import auth, student, teacher
from shared import kafka, storage


@asynccontextmanager
async def lifespan(app):
    storage.ensure_bucket()
    kafka.ensure_topics()
    yield


app = FastAPI(title="Scribe-Check", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(teacher.router)
app.include_router(student.router)


@app.get("/api/health")
def health():
    return {"ok": True}


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
