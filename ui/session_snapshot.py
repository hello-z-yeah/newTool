import json
from pathlib import Path

class SessionSnapshot:
    """Helper class to persist simple JSON state between app runs.
    The file is stored under the user's config directory (e.g. ~/.config/newTool).
    """
    def __init__(self, filename: str = "session_snapshot.json"):
        self.base_dir = Path.home() / ".config" / "newTool"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.base_dir / filename
        self.state: dict = {}
        self._load()

    def _load(self):
        if self.file_path.exists():
            try:
                with self.file_path.open("r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except Exception:
                self.state = {}

    def save(self):
        with self.file_path.open("w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        return self.state.get(key, default)

    def set(self, key, value):
        self.state[key] = value
        self.save()
