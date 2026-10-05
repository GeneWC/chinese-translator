"""Development-time asset pinning. Run deliberately, never on app startup."""
import hashlib
import json
from pathlib import Path
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "chinese_screen_dictionary" / "assets"
MODELS = ROOT / ".test-data" / "models"
ASSETS.mkdir(parents=True, exist_ok=True)
MODELS.mkdir(parents=True, exist_ok=True)
BASE = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx"
items = [
    ("ch_PP-OCRv5_det_mobile.onnx", "Chinese text detection", f"{BASE}/PP-OCRv5/det/ch_PP-OCRv5_det_mobile.onnx", "onnx", "4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae"),
    ("ch_PP-OCRv5_rec_server.onnx", "Chinese text recognition", f"{BASE}/PP-OCRv5/rec/ch_PP-OCRv5_rec_server.onnx", "onnx", "e09385400eaaaef34ceff54aeb7c4f0f1fe014c27fa8b9905d4709b65746562a"),
    ("ch_ppocr_mobile_v2.0_cls_mobile.onnx", "Text orientation", f"{BASE}/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx", "onnx", "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c"),
    ("translate-zh_en-1_9.argosmodel", "Simplified Chinese translation", "https://argos-net.com/v1/translate-zh_en-1_9.argosmodel", "argos", None),
    ("translate-zt_en-1_9.argosmodel", "Traditional Chinese translation", "https://argos-net.com/v1/translate-zt_en-1_9.argosmodel", "argos", None),
]


def fetch(url, path):
    if path.exists():
        return
    print(f"Downloading {path.name}", flush=True)
    with requests.get(url, stream=True, timeout=(20, 90)) as response:
        response.raise_for_status()
        temp = path.with_suffix(path.suffix + ".part")
        with temp.open("wb") as out:
            for chunk in response.iter_content(1024*1024):
                out.write(chunk)
        temp.replace(path)


manifest = []
for name, label, url, kind, expected in items:
    path = MODELS / name
    fetch(url, path)
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if expected and expected != digest:
        raise ValueError(f"Hash mismatch: {name}")
    manifest.append(dict(name=name, label=label, url=url, kind=kind, sha256=digest, size=path.stat().st_size))
    print(f"Verified {name}: {path.stat().st_size} bytes", flush=True)
(ASSETS / "models.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
dictionary = ASSETS / "cedict.txt.gz"
fetch("https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz", dictionary)
with dictionary.open("rb") as stream:
    sha = hashlib.file_digest(stream, "sha256").hexdigest()
(ASSETS / "dictionary.json").write_text(json.dumps({"source": "https://www.mdbg.net/chinese/dictionary?page=cedict",
    "sha256": sha, "license": "CC-BY-SA-4.0"}, indent=2), encoding="utf-8")
print("Pinned models and dictionary snapshot.", flush=True)
