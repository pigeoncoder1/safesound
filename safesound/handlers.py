from .policy import allowed


def is_about_owner(person: str | None, owner: str | None) -> bool:
    return person is None or (owner is not None and person.lower() == owner.lower())


def read_messages(command, speaker, room_state, owner):
    return {"level": allowed(speaker["relationship"], "messages", room_state)}


def where_is(command, speaker, room_state, owner):
    if not is_about_owner(command["person"], owner):
        return {"level": "none", "reason": "only knows about the owner"}
    return {"level": allowed(speaker["relationship"], "location", room_state)}


def is_free(command, speaker, room_state, owner):
    if not is_about_owner(command["person"], owner):
        return {"level": "none", "reason": "only knows about the owner"}
    return {"level": allowed(speaker["relationship"], "calendar", room_state)}


def leave_message(command, speaker, room_state, owner):
    return {"level": "accept" if command["text"] else "ask_for_text"}


def introduce(command, speaker, room_state, owner):
    if speaker["relationship"] != "owner":
        return {"level": "none", "reason": "only the owner can introduce people"}
    return {"level": "accept" if command["relationship"] else "ask_for_relationship"}


def digest(command, speaker, room_state, owner):
    if speaker["relationship"] != "owner" or room_state != "private":
        return {"level": "none"}
    return {"level": "full"}


HANDLERS = {
    "read_messages": read_messages,
    "where_is": where_is,
    "is_free": is_free,
    "leave_message": leave_message,
    "introduce": introduce,
    "digest": digest,
}


def route(command: dict, speaker: dict, room_state: str, owner: str | None) -> dict:
    decision = HANDLERS[command["intent"]](command, speaker, room_state, owner)
    return {"type": "command", **command, "speaker": speaker["label"], **decision}
