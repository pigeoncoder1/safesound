import json
from pathlib import Path

PEOPLE_FILE = Path(__file__).resolve().parent.parent / "data" / "people.json"


def load_people(path: Path = PEOPLE_FILE) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def lookup(label: str, people: list[dict]) -> dict:
    for person in people:
        if Path(person["voice_file"]).stem == label:
            return {"name": person["name"], "relationship": person["relationship"]}
    return {"name": None, "relationship": "unknown"}


def owner_name(people: list[dict]) -> str | None:
    return next((p["name"] for p in people if p["relationship"] == "owner"), None)
