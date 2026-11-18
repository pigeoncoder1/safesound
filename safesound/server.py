from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="safesound")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run("safesound.server:app", host=settings.host, port=settings.port, reload=True)
