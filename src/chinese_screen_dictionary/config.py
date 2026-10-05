import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


def data_dir() -> Path:
    override = os.environ.get("CSD_DATA_DIR")
    path = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ChineseScreenDictionary"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Settings:
    capture_hotkey: str = "Ctrl+Alt+D"
    library_hotkey: str = "Ctrl+Alt+L"
    selection_mode: str = "rectangle"
    start_with_windows: bool = False

    @classmethod
    def load(cls, root: Path):
        try:
            data = json.loads((root / "settings.json").read_text(encoding="utf-8"))
            allowed = {f.name for f in fields(cls)}
            result = cls(**{k: v for k, v in data.items() if k in allowed})
            if result.selection_mode not in ("rectangle", "lasso"):
                result.selection_mode = "rectangle"
            if not isinstance(result.capture_hotkey, str) or not isinstance(result.library_hotkey, str) or not isinstance(result.start_with_windows, bool):
                return cls()
            return result
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()

    def save(self, root: Path):
        temp = root / "settings.json.tmp"
        temp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        temp.replace(root / "settings.json")
