import argparse
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import llm
from .activity import clear_activity, deliver_digest, load_activity, log_interaction, mark_delivered
from .calls import call_status, current_call, effective_relationship, end_call, find_person, start_call, verify_caller
from .commands import addressed_to_assistant, is_fragment, only_wake_word, understand
from .config import settings
from .demo import (
    DEMO_DIR, DEMO_NAMES, FRAME_SAMPLES, PAUSE_BETWEEN_LINES, PAUSE_BETWEEN_SCENES, SCENES, call_ends_after,
    lines_needing_llm, missing_files, pcm_frames, playable_scenes, readiness_report,
)
from .introductions import Introduction, problem_with
from .listener import Listener
from .owner_setup import ENROL_PROMPT, OwnerSetup, clean_name, owner_enrolled
from .owner_setup import TARGET_SECONDS as OWNER_SETUP_SECONDS
from .people import load_people, lookup, owner_name, remove_person
from .reply import Context, load_world, respond
from .room import RoomState
from .speaker import SAMPLE_RATE, VOICES_DIR
from .speaker import load_model as load_speaker_model
from .stt import load_model as load_whisper_model

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
ROOM_TICK_SECONDS = 1.0
ACTIVITY_SHOWN = 30
TTS_START_WAIT_SECONDS = 3.0
TTS_MAX_SECONDS = 90.0

log = logging.getLogger("safesound.server")
people_changes = {"version": 0}


def people_changed() -> None:
    people_changes["version"] += 1


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


@app.get("/api/demo")
def demo_state() -> dict:
    people = load_people()
    return {
        "owner": owner_name(people),
        "people": [{"name": p["name"], "relationship": p["relationship"], "label": Path(p["voice_file"]).stem} for p in people],
        "llm": {"on": llm.PROVIDER != "none", "provider": llm.PROVIDER},
        "world": load_world(),
        "activity": load_activity()[-ACTIVITY_SHOWN:],
        "activity_total": len(load_activity()),
        "demo": demo_info(owner_name(people) or "the owner"),
        "owner_enrolled": owner_enrolled(),
        "setup": {"prompt": ENROL_PROMPT, "seconds": OWNER_SETUP_SECONDS},
    }


def demo_info(owner: str) -> dict:
    required, optional = missing_files()
    return {
        "on": settings.demo_mode,
        "scenes": [{"number": s.number, "title": s.heading(owner)} for s in SCENES],
        "missing": required,
        "missing_optional": optional,
        "needs_llm": [s.number for s, _ in lines_needing_llm(owner)],
    }


@app.delete("/api/people/{label}")
def delete_person(label: str) -> dict:
    removed = remove_person(label, VOICES_DIR)
    if removed is None:
        raise HTTPException(status_code=404, detail="No such person, or that is the owner.")
    people_changed()
    return {"removed": removed["name"]}


@app.delete("/api/activity")
def delete_activity() -> dict:
    return {"cleared": clear_activity()}


@app.websocket("/ws")
async def audio_socket(ws: WebSocket) -> None:
    await ws.accept()
    listener = Listener(extra_names=DEMO_NAMES if settings.demo_mode else None)
    room = RoomState()
    people = load_people()
    last_sent = None
    intro: Introduction | None = None
    owner_last_spoke: float | None = None
    demo_task: asyncio.Task | None = None
    owner_setup: OwnerSetup | None = None
    people_seen = people_changes["version"]
    says = 0
    tts_started = asyncio.Event()
    tts_finished = asyncio.Event()

    async def say(text: str) -> None:
        nonlocal says
        says += 1
        tts_started.clear()
        tts_finished.clear()
        await ws.send_json({"type": "say", "text": text})

    async def begin_call(caller_id: str | None) -> None:
        if current_call() is None:
            start_call(caller_id)
        await ws.send_json(call_status(people))

    async def finish_call() -> None:
        end_call()
        await ws.send_json(call_status(people))

    async def welcome_back_digest() -> str | None:
        if room.state(time.monotonic()) != "private":
            return None
        delivered = await asyncio.to_thread(deliver_digest)
        if delivered is None:
            return None
        text, ids = delivered
        await ws.send_json({"type": "digest_delivered", "ids": ids})
        return text

    async def finish_intro(current: Introduction) -> None:
        line = await asyncio.to_thread(current.finish)
        if current.stage == "done":
            listener.reload_people()
            people[:] = load_people()
            people_changed()
        await ws.send_json(current.status())
        await say(line)

    async def expire_intro_if_due() -> None:
        nonlocal intro
        if intro is None or not intro.timed_out(time.monotonic()):
            return
        current, intro = intro, None
        if current.stage == "collecting":
            await finish_intro(current)
        else:
            line = current.cancel()
            await ws.send_json(current.status())
            await say(line)

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
            await expire_intro_if_due()

    async def handle_segment(segment) -> None:
        nonlocal intro, owner_last_spoke, people_seen
        if people_seen != people_changes["version"]:
            people_seen = people_changes["version"]
            listener.reload_people()
            people[:] = load_people()
        heard = await asyncio.to_thread(listener.analyse, segment)
        if heard is None:
            return

        call = current_call()
        channel = "call" if call else "room"
        await ws.send_json({"type": "voice", "channel": channel, **{k: heard[k] for k in ("label", "score", "seconds", "reliable")}})

        if intro and channel == "room" and intro.wants(heard["label"]):
            if intro.add(segment):
                current, intro = intro, None
                await finish_intro(current)
            else:
                await ws.send_json(intro.status())
            return

        heard["text"] = await asyncio.to_thread(listener.transcribe, segment)

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

        digest_due = False
        if channel == "room" and speaker["relationship"] == "owner":
            now = time.monotonic()
            digest_due = owner_last_spoke is None or now - owner_last_spoke >= settings.digest_away_minutes * 60
            owner_last_spoke = now

        async def send_transcript(path: str) -> None:
            await ws.send_json({
                "type": "transcript",
                "channel": channel,
                "speaker": speaker["label"],
                "name": speaker["name"],
                "relationship": speaker["relationship"],
                "text": heard["text"],
                "path": path,
            })

        if intro and intro.stage == "asking" and channel == "room" and speaker["relationship"] == "owner":
            await send_transcript("answer")
            line = intro.hear_answer(heard["text"], time.monotonic())
            await ws.send_json(intro.status())
            if intro.stage == "cancelled":
                intro = None
            await say(line)
            return

        known_names = [p["name"] for p in people]
        command, path = await asyncio.to_thread(understand, heard["text"], known_names)
        ignored = path == "unclear" and (only_wake_word(heard["text"]) or is_fragment(heard["text"])
                                         or (channel == "room" and not addressed_to_assistant(heard["text"])))
        await send_transcript("ignored" if ignored else path)

        if ignored:
            if digest_due and (summary := await welcome_back_digest()):
                await say(f"Welcome back. {summary}")
            return
        await ws.send_json({"type": "command", "channel": channel, "speaker": speaker["label"], **command})

        if command["intent"] == "introduce" and channel == "room" and speaker["relationship"] == "owner":
            problem = problem_with(command.get("name"), owner_name(people))
            if problem:
                await say(problem)
                return
            intro = Introduction(command["name"], command.get("relationship"), time.monotonic())
            await ws.send_json(intro.status())
            await say(intro.opening_line())
            return

        ctx = Context(
            speaker_name=speaker["name"],
            speaker_label=speaker["label"],
            caller_id=call.caller_id if call else None,
            verification=verification,
            owner=owner_name(people),
        )
        answer = await asyncio.to_thread(respond, command, speaker["relationship"], channel, room.state(time.monotonic()), ctx)
        text = answer["text"]
        if command["intent"] == "digest" and speaker["relationship"] == "owner" and answer["disclosed"]:
            await ws.send_json({"type": "digest_delivered", "ids": answer["disclosed"]})
        elif digest_due and (summary := await welcome_back_digest()):
            text = f"{text} Also, while you were away: {summary}"
        await say(text)
        await ws.send_json({
            "type": "disclosure",
            "intent": command["intent"],
            "channel": channel,
            "speaker": speaker["name"] or speaker["label"],
            "relationship": speaker["relationship"],
            "disclosed": answer["disclosed"],
            "rough": answer["rough"],
            "withheld": answer["withheld"],
        })

        if speaker["relationship"] != "owner":
            entry = await asyncio.to_thread(
                log_interaction,
                channel=channel,
                session=f"call-{call.started_at}" if call else None,
                caller_id=call.caller_id if call else None,
                voice=speaker["label"],
                name=speaker["name"],
                relationship=speaker["relationship"],
                verification=verification,
                heard=heard["text"],
                intent=command["intent"],
                earshot_said=answer["text"],
                disclosed=answer["disclosed"],
                message_left=(command.get("text") or None) if command["intent"] == "leave_message" else None,
            )
            await ws.send_json({"type": "activity", "entry": entry})

    async def wait_until_spoken() -> None:
        try:
            await asyncio.wait_for(tts_started.wait(), TTS_START_WAIT_SECONDS)
        except asyncio.TimeoutError:
            await asyncio.sleep(1.0)
            return
        try:
            await asyncio.wait_for(tts_finished.wait(), TTS_MAX_SECONDS)
        except asyncio.TimeoutError:
            pass

    async def play_line(path: Path) -> None:
        frame_seconds = FRAME_SAMPLES / SAMPLE_RATE
        for frame in await asyncio.to_thread(pcm_frames, path):
            for segment in listener.feed(frame):
                await handle_segment(segment)
            await asyncio.sleep(frame_seconds)

    async def run_demo() -> None:
        required, _ = missing_files()
        if required:
            await ws.send_json({"type": "demo", "state": "error", "message": "Missing recordings: " + ", ".join(required)})
            return
        owner = owner_name(people) or "the owner"
        scenes = playable_scenes()
        earlier = [e["id"] for e in load_activity() if not e["delivered"]]
        if earlier:
            await asyncio.to_thread(mark_delivered, earlier)
        await ws.send_json({"type": "demo", "state": "started", "scenes": len(scenes), "cleared": len(earlier)})

        for index, scene in enumerate(scenes):
            print(f"[demo] Scene {scene.number}: {scene.heading(owner)}", flush=True)
            await ws.send_json({"type": "demo_scene", "number": scene.number, "title": scene.heading(owner),
                                "channel": scene.channel, "caller_id": scene.caller_id})
            if scene.channel == "room" and current_call():
                await finish_call()
            if scene.channel == "call" and not (scene.continues_call and current_call()):
                if current_call():
                    await finish_call()
                await begin_call(scene.caller_id)

            for line in scene.lines:
                before = says
                await play_line(DEMO_DIR / line.file)
                if says > before:
                    await wait_until_spoken()
                await asyncio.sleep(PAUSE_BETWEEN_LINES)

            if call_ends_after(index, scenes):
                await finish_call()
            await asyncio.sleep(PAUSE_BETWEEN_SCENES)

        print("[demo] Done", flush=True)
        await ws.send_json({"type": "demo", "state": "done"})

    async def run_demo_safely() -> None:
        try:
            await run_demo()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.exception("Demo failed")
            await ws.send_json({"type": "demo", "state": "error", "message": str(error)})

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
                    tts_started.set()
                elif kind == "tts_end":
                    listener.unmute()
                    tts_finished.set()
                elif kind == "call_start":
                    caller_id = data.get("caller_id")
                    await begin_call(caller_id if isinstance(caller_id, str) else None)
                elif kind == "call_end":
                    await finish_call()
                elif kind == "owner_setup_start":
                    name = clean_name(data.get("name"))
                    if name is None:
                        await ws.send_json({"type": "owner_setup", "stage": "failed",
                                            "message": "Please type your name (letters only)."})
                    else:
                        owner_setup = OwnerSetup(name)
                        await ws.send_json(owner_setup.status())
                elif kind == "owner_setup_cancel":
                    owner_setup = None
                    await ws.send_json({"type": "owner_setup", "stage": "cancelled"})
                elif kind == "demo_start" and settings.demo_mode and (demo_task is None or demo_task.done()):
                    demo_task = asyncio.create_task(run_demo_safely())
                continue

            if message.get("bytes") and owner_setup is not None:
                if owner_setup.add(message["bytes"]):
                    current, owner_setup = owner_setup, None
                    result = await asyncio.to_thread(current.finish)
                    if current.stage == "done":
                        listener.reload_people()
                        people[:] = load_people()
                        people_changed()
                    await ws.send_json(current.status(result))
                elif owner_setup.progress_due():
                    await ws.send_json(owner_setup.status())
                continue

            if message.get("bytes") and not settings.demo_mode:
                for segment in listener.feed(message["bytes"]):
                    await handle_segment(segment)
    except WebSocketDisconnect:
        pass
    finally:
        ticker.cancel()
        if demo_task:
            demo_task.cancel()
        end_call()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the safesound server.")
    parser.add_argument("--demo", action="store_true", help="play the scripted recordings in data/demo/ instead of the mic")
    args = parser.parse_args()

    if args.demo:
        os.environ["DEMO_MODE"] = "1"
        owner = owner_name(load_people()) or "the owner"
        print(f"Demo mode: open http://{settings.host}:{settings.port}, press Connect, then Play demo.")
        if not owner_enrolled():
            print("WARNING: no owner voice is enrolled. Run python -m safesound.server once and complete the setup screen.")
        for warning in readiness_report(owner, llm_on=llm.PROVIDER != "none"):
            print(f"WARNING: {warning}")

    uvicorn.run("safesound.server:app", host=settings.host, port=settings.port, reload=True)


if __name__ == "__main__":
    main()
