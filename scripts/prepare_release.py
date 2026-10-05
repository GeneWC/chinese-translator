"""Copy readable documentation and dependency license files into the release."""
from importlib.metadata import distributions
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
release = root / "dist/ChineseScreenDictionary"
if not (release / "ChineseScreenDictionary.exe").exists():
    raise SystemExit("Build the executable first.")
for name in ("README.md", "THIRD_PARTY_NOTICES.md"):
    shutil.copy2(root / name, release / name)
licenses = release / "licenses"
for distribution in distributions():
    name = distribution.metadata["Name"]
    for relative in distribution.files or []:
        if relative.name.lower().startswith(("license", "copying", "notice")) or "licenses" in relative.parts:
            source = Path(distribution.locate_file(relative))
            if source.is_file():
                target = licenses / name / str(relative).replace("..", "_")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
print(f"Release ready: {release}")
