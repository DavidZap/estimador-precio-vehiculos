import json
from pathlib import Path
from typing import Any


class LocalFileStorage:
    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str) -> Path:
        path = self.base_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, relative_path: str, payload: dict[str, Any]) -> Path:
        path = self.resolve(relative_path)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_text(self, relative_path: str, payload: str) -> Path:
        path = self.resolve(relative_path)
        path.write_text(payload, encoding="utf-8")
        return path
