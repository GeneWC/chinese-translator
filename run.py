"""PyInstaller entry point, including a useful log for startup failures."""
import os
from pathlib import Path
import sys
import traceback

if __name__ == "__main__":
    try:
        from chinese_screen_dictionary.app import main
        main()
    except Exception:
        folder = Path(os.environ.get("CSD_DATA_DIR") or str(Path(os.environ["LOCALAPPDATA"]) / "ChineseScreenDictionary"))
        folder.mkdir(parents=True, exist_ok=True)
        failure = folder / "startup-error.log"
        failure.write_text(traceback.format_exc(), encoding="utf-8")
        if "--self-test" not in sys.argv and "--download-models" not in sys.argv:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"The app could not start. Details were saved to:\n{failure}",
                                             "Chinese Screen Dictionary", 0x10)
        sys.exit(1)
