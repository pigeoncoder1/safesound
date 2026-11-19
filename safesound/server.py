import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .calls import call_status, current_call, effective_relationship, end_call, find_person, start_call, verify_caller
from .commands import addressed_to_assistant, understand
from .config import settings
from .listener import Listener
from .people import load_people, lookup, owner_name
from .reply import Context, respond
from .room import RoomState
from .speaker import load_model as load_speaker_model
from .stt import load_model as load_whisper_model

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
ROOM_TICK_SECONDS = 1.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(load_speaker_model)
    await asyncio.to_thread(load_whisper_model)
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
    people = load_people()
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

    async def handle_segment(segment) -> None:
        heard = await asyncio.to_thread(listener.analyse, segment)
        if heard is None:
            return

        call = current_call()
        channel = "call" if call else "room"
        await ws.send_json({"type": "voice", "channel": channel, **{k: heard[k] for k in ("label", "score", "seconds", "reliable")}})

        if call:
            before = call_status(people)
            call.voice_labels.append(heard["label"])
            if call_status(people) != before:
                await ws.send_json(call_status(people))
            verification = verify_caller(call.caller_id, heard["label"], people)
            relationship = effective_relationship(call.caller_id, heard["label"], people)
            name = find_person(call.caller_id, people)["name"] if verification == "verified" else None
            speaker = {"label": heard["label"], "name": name, "relationship": relationship}
        else:
            verification = "in_person"
            if heard["reliable"]:
                room.observe(heard["label"], time.monotonic())
                await push_room_if_changed()
            speaker = {"label": heard["label"], **lookup(heard["label"], people)}

        if not heard["text"]:
            return
        known_names = [p["name"] for p in people]
        command, path = await asyncio.to_thread(understand, heard["text"], known_names)
        await ws.send_json({
            "type": "transcript",
            "channel": channel,
            "speaker": speaker["label"],
            "name": speaker["name"],
            "relationship": speaker["relationship"],
            "text": heard["text"],
            "path": path,
        })

        if path == "unclear" and channel == "room" and not addressed_to_assistant(heard["text"]):
            return
        await ws.send_json({"type": "command", "channel": channel, "speaker": speaker["label"], **command})

        ctx = Context(
            speaker_name=speaker["name"],
            speaker_label=speaker["label"],
            caller_id=call.caller_id if call else None,
            verification=verification,
            owner=owner_name(people),
        )
        answer = await asyncio.to_thread(respond, command, speaker["relationship"], channel, room.state(time.monotonic()), ctx)
        await ws.send_json({"type": "say", "text": answer["text"]})
        await ws.send_json({"type": "disclosure", "disclosed": answer["disclosed"], "withheld": answer["withheld"]})

    await push_room_if_changed()
    await ws.send_json(call_status(people))
    ticker = asyncio.create_task(tick())
    try:
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                break

            if message.get("text"):
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                if not isinstance(data, dict):
                    continue
                kind = data.get("type")
                if kind == "tts_start":
                    listener.mute()
                elif kind == "tts_end":
                    listener.unmute()
                elif kind == "call_start":
                    if current_call() is None:
                        caller_id = data.get("caller_id")
                        start_call(caller_id if isinstance(caller_id, str) else None)
                    await ws.send_json(call_status(people))
                elif kind == "call_end":
                    end_call()
                    await ws.send_json(call_status(people))
                continue

            if message.get("bytes"):
                for segment in listener.feed(message["bytes"]):
                    await handle_segment(segment)
    except WebSocketDisconnect:
        pass
    finally:
        ticker.cancel()
        end_call()


if __name__ == "__main__":
    uvicorn.run("safesound.server:app", host=settings.host, port=settings.port, reload=True)
