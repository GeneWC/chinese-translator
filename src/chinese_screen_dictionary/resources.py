import hashlib
import json
import time
import zipfile
from pathlib import Path

import requests

ASSETS = Path(__file__).parent / "assets"


def digest(path: Path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest():
    return json.loads((ASSETS / "models.json").read_text(encoding="utf-8"))


def package_path(root: Path, code: str) -> Path:
    folder = root / "models" / f"translate-{code}_en-1_9"
    candidates = sorted(folder.rglob("metadata.json")) if folder.exists() else []
    for meta in candidates:
        if (meta.parent / "model" / "model.bin").is_file() and (meta.parent / "sentencepiece.model").is_file():
            return meta.parent
    raise FileNotFoundError(f"Missing {code}-to-English model. Open Download / repair models from the tray.")


def models_ready(root: Path) -> bool:
    try:
        marker = json.loads((root / "models" / "ready.json").read_text(encoding="utf-8"))
        if marker != {item["name"]: item["sha256"] for item in manifest()}:
            return False
        for item in manifest():
            path = root / "models" / item["name"]
            if not path.is_file() or path.stat().st_size != item["size"]:
                return False
        package_path(root, "zh")
        package_path(root, "zt")
        return True
    except (OSError, ValueError, KeyError):
        return False


def safe_extract(archive: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    resolved = destination.resolve()
    with zipfile.ZipFile(archive) as zf:
        for item in zf.infolist():
            target = (destination / item.filename).resolve()
            if not target.is_relative_to(resolved) or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Unsafe path in model archive")
        zf.extractall(destination)


def ensure_models(root: Path, progress=lambda message, percent: None):
    folder = root / "models"
    folder.mkdir(parents=True, exist_ok=True)
    items = manifest()
    total = sum(item["size"] for item in items)
    completed = 0
    for item in items:
        target = folder / item["name"]
        progress(f'Checking {item["label"]}…', int(completed/total*100))
        valid = target.exists() and digest(target) == item["sha256"]
        if not valid:
            temporary = target.with_suffix(target.suffix + ".part")
            for attempt in range(3):
                try:
                    with requests.get(item["url"], stream=True, timeout=(20, 45)) as response:
                        response.raise_for_status()
                        received = 0
                        last_update = 0
                        with temporary.open("wb") as out:
                            for chunk in response.iter_content(256*1024):
                                out.write(chunk)
                                received += len(chunk)
                                if time.monotonic()-last_update > .15:
                                    percent = int(min(99, (completed+received)/total*100))
                                    progress(f'{item["label"]}: {received/1048576:.1f} / {item["size"]/1048576:.1f} MB', percent)
                                    last_update = time.monotonic()
                    if digest(temporary) != item["sha256"]:
                        raise ValueError(f'{item["label"]} failed its integrity check. Retry the download.')
                    temporary.replace(target)
                    break
                except (requests.RequestException, OSError, ValueError):
                    if attempt == 2:
                        raise
                    time.sleep(attempt+1)
        if item.get("kind") == "argos":
            progress(f'Installing {item["label"]}…', int(completed/total*100))
            safe_extract(target, folder / target.stem)
        completed += item["size"]
    marker = folder / "ready.json.tmp"
    marker.write_text(json.dumps({item["name"]: item["sha256"] for item in items}), encoding="utf-8")
    marker.replace(folder / "ready.json")
    progress("All language models are ready.", 100)
