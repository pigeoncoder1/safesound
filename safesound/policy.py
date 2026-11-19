PERMISSIONS = {
    "owner":   {"messages": "full", "location": "full",  "calendar": "full"},
    "partner": {"messages": "none", "location": "full",  "calendar": "full"},
    "friend":  {"messages": "none", "location": "rough", "calendar": "rough"},
    "unknown": {"messages": "none", "location": "none",  "calendar": "none"},
}

INFO_TYPES = ("messages", "location", "calendar")
LEVELS = ("full", "rough", "none")


def allowed(relationship: str, info_type: str, room_state: str) -> str:
    if info_type not in INFO_TYPES:
        raise ValueError(f"unknown info type: {info_type!r}")

    level = PERMISSIONS.get(relationship, PERMISSIONS["unknown"])[info_type]

    if level == "full" and room_state != "private":
        return "rough"
    return level


def visible_messages(inbox: list[dict], level: str) -> list[dict]:
    if level == "full":
        return list(inbox)
    if level == "rough":
        return [m for m in inbox if not m["sensitive"]]
    return []
