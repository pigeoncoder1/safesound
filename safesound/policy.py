PERMISSIONS = {
    "owner":   {"messages": "full", "location": "full",  "calendar": "full"},
    "partner": {"messages": "full", "location": "full",  "calendar": "full"},
    "friend":  {"messages": "rough", "location": "rough", "calendar": "rough"},
    "unknown": {"messages": "none", "location": "none",  "calendar": "none"},
}

INFO_TYPES = ("messages", "location", "calendar")
LEVELS = ("full", "rough", "none")
CUSTOMISABLE = ("partner", "friend")


def permissions_for(relationship: str, overrides: dict | None = None) -> dict:
    levels = dict(PERMISSIONS.get(relationship, PERMISSIONS["unknown"]))
    if relationship in CUSTOMISABLE and isinstance(overrides, dict):
        for info_type in INFO_TYPES:
            if overrides.get(info_type) in LEVELS:
                levels[info_type] = overrides[info_type]
    return levels


def allowed(relationship: str, info_type: str, room_state: str, overrides: dict | None = None) -> str:
    if info_type not in INFO_TYPES:
        raise ValueError(f"unknown info type: {info_type!r}")

    level = permissions_for(relationship, overrides)[info_type]

    if level == "full" and room_state != "private":
        return "rough"
    return level


def visible_messages(inbox: list[dict], level: str) -> list[dict]:
    if level == "full":
        return list(inbox)
    if level == "rough":
        return [m for m in inbox if not m["sensitive"]]
    return []


LEVEL_ORDER = {"none": 0, "rough": 1, "full": 2}
STRANGER_CAP = "rough"


def lowest(*levels: str) -> str:
    return min(levels, key=LEVEL_ORDER.__getitem__)


def listener_cap(info_type: str, listeners: list[dict], room_state: str) -> str:
    caps = ["full"]
    if room_state != "private":
        caps.append(STRANGER_CAP)
    for listener in listeners:
        caps.append(permissions_for(listener["relationship"], listener.get("permissions"))[info_type])
    return lowest(*caps)
