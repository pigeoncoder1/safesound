from datetime import datetime


def now_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def to_minutes(hhmm: str) -> int:
    hours, mins = hhmm.split(":")
    return int(hours) * 60 + int(mins)


def spoken_time(hhmm: str) -> str:
    hours, mins = (int(x) for x in hhmm.split(":"))
    hour12 = hours % 12 or 12
    return f"{hour12}" if mins == 0 else f"{hour12}:{mins:02d}"
