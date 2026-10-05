# Build with: .venv\Scripts\pyinstaller.exe --noconfirm ChineseScreenDictionary.spec
from pathlib import Path
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

project = Path(SPECPATH)
# An activated Conda installation can supply incompatible CRT / OpenSSL DLLs.
# Keep dependency discovery local to this venv, its CPython base, and Windows.
os.environ["PATH"] = os.pathsep.join([
    str(Path(sys.executable).parent), sys.base_prefix,
    str(Path(sys.base_prefix) / "DLLs"),
    str(Path(os.environ["SystemRoot"]) / "System32"), os.environ["SystemRoot"],
])
datas = [(str(project / "src/chinese_screen_dictionary/assets"), "chinese_screen_dictionary/assets"),
         (str(project / "THIRD_PARTY_NOTICES.md"), "."),
         (str(project / "README.md"), ".")]
for package in ("rapidocr", "jieba", "pypinyin", "argostranslate"):
    datas += collect_data_files(package, excludes=["**/models/*.onnx", "**/test*", "**/lac_small/**"])
for distribution in ("rapidocr", "argostranslate", "ctranslate2", "onnxruntime", "requests", "jieba", "pypinyin"):
    datas += copy_metadata(distribution)
binaries = collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("onnxruntime")
a = Analysis([str(project / "run.py")], pathex=[str(project / "src")],
    binaries=binaries, datas=datas,
    hiddenimports=["rapidocr.inference_engine.onnxruntime", "rapidocr.inference_engine.onnxruntime.main",
                   "argostranslate.package", "pypinyin.contrib.tone_convert"],
    excludes=["torch", "torchvision", "torchaudio", "spacy", "stanza", "tensorflow", "paddle", "openvino",
              "matplotlib", "IPython", "pytest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ChineseScreenDictionary", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(project / "src/chinese_screen_dictionary/assets/app.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ChineseScreenDictionary")
