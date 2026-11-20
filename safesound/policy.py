PERMISSIONS = {
    "owner":   {"messages": "full", "location": "full",  "calendar": "full"},
    "partner": {"messages": "none", "location": "full",  "calendar": "full"},
    "friend":  {"messages": "none", "location": "rough", "calendar": "rough"},
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
