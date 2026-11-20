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


def save_people(people: list[dict], path: Path = PEOPLE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(people, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def upsert_person(name: str, relationship: str, voice_file: str, path: Path = PEOPLE_FILE) -> list[dict]:
    people = [p for p in load_people(path) if p["name"].lower() != name.lower() and p["voice_file"] != voice_file]
    people.append({"name": name, "relationship": relationship, "voice_file": voice_file})
    save_people(people, path)
    return people


def remove_person(label: str, voices_dir: Path, path: Path = PEOPLE_FILE) -> dict | None:
    people = load_people(path)
    match = next((p for p in people if Path(p["voice_file"]).stem == label), None)
    if match is None or match["relationship"] == "owner":
        return None
    save_people([p for p in people if p is not match], path)
    voice = voices_dir / Path(match["voice_file"]).name
    if voice.exists():
        voice.unlink()
    return match


def permissions_of(label: str, people: list[dict]) -> dict | None:
    person = next((p for p in people if Path(p["voice_file"]).stem == label), None)
    return person.get("permissions") if person else None


def update_person(label: str, relationship: str | None, permissions: dict | None,
                  path: Path = PEOPLE_FILE) -> dict | None:
    people = load_people(path)
    person = next((p for p in people if Path(p["voice_file"]).stem == label), None)
    if person is None or person["relationship"] == "owner":
        return None
    if relationship is not None:
        person["relationship"] = relationship
        person.pop("permissions", None)
    if permissions is not None:
        person["permissions"] = dict(permissions)
    save_people(people, path)
    return person
