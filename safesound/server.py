import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .listener import Listener
from .room import RoomState
from .speaker import load_model

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
ROOM_TICK_SECONDS = 1.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(load_model)
    yield


app = FastAPI(title="safesound", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.websocket("/ws")
async def audio_socket(ws: WebSocket) -> None:
    await ws.accept()
    listener = Listener()
    room = RoomState()
    last_sent = None

    async def push_room_if_changed() -> None:
        nonlocal last_sent
        now = time.monotonic()
        key = room.change_key(now)
        if key != last_sent:
            last_sent = key
            await ws.send_json(room.snapshot(now))

    async def tick() -> None:
        while True:
            await asyncio.sleep(ROOM_TICK_SECONDS)
            await push_room_if_changed()

    await push_room_if_changed()
    ticker = asyncio.create_task(tick())
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break

            if message.get("text"):
                try:
                    kind = json.loads(message["text"]).get("type")
                except json.JSONDecodeError:
                    continue
                if kind == "tts_start":
                    listener.mute()
                elif kind == "tts_end":
                    listener.unmute()
                continue

            if message.get("bytes"):
                for segment in listener.feed(message["bytes"]):
                    result = await asyncio.to_thread(listener.classify, segment)
                    await ws.send_json(result)
                    if result["type"] == "voice":
                        room.observe(result["label"], time.monotonic())
                        await push_room_if_changed()
    except WebSocketDisconnect:
        pass
    finally:
        ticker.cancel()


if __name__ == "__main__":
    uvicorn.run("safesound.server:app", host=settings.host, port=settings.port, reload=True)
