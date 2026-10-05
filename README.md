# Chinese Screen Dictionary

A free Windows tray app for reading Chinese in images. Select a character, phrase,
or speech bubble anywhere on your desktop to see Chinese, tone-colored pinyin,
an English translation, and dictionary definitions. Your vocabulary is saved locally.

## Start the app

Open **ChineseScreenDictionary.exe** in `dist/ChineseScreenDictionary`.
Keep the executable together with its `_internal` folder. You do not need Python
to use this portable build. The yellow **中** icon appears in the Windows system
tray (possibly under the tray's up-arrow).
If you cloned the source from GitHub, follow **Develop and test** below to build
the portable folder first.

On a new computer, click **Download models** in the setup window. This downloads
about **228 MiB** of verified OCR and translation models; allow about **450 MiB**
of storage for their archives and installed files. If a download fails, use Retry.
The dictionary is included with the app. After setup, lookups do not need internet.

1. Press **Ctrl+Alt+D**.
2. Choose **Rectangle (R)** or **Lasso (L)** and drag around the Chinese text.
3. Release the mouse. A yellow note shows the reading, translation, and definitions.
4. Press **Ctrl+Alt+D** again to dismiss the note. Press it once more for a new selection.
5. Press **Ctrl+Alt+L** to open your saved dictionary.

Escape or right-click cancels selection. Escape also closes a focused note.
The note stays open while you read and can be dragged by its title. Use **Edit text**
to fix recognition, or change **Auto / Horizontal / Vertical** to correct reading
order. Vertical text reads top-to-bottom, columns right-to-left. Editing the text
locks in that order; take a new selection if you want to return to the original OCR.

Use **Settings** in the tray menu to change the shortcuts or opt into starting
with Windows. The app starts manually by default. Use **Quit** in the tray menu
to close it completely. If a model is damaged, choose **Download / repair models**.

## Vocabulary behavior

- Each distinct word or phrase counts once per successful selection, even if it
  appears more than once in that selection.
- Sentences contribute multi-character words and dictionary phrases. For example,
  `我喜欢学习中文` contributes `喜欢`, `学习`, and `中文`.
- A single character is saved only when looked up alone, including surrounding
  punctuation. It appears in the **Single characters** tab.
- Explicit CC-CEDICT simplified/traditional pairs share a count. The source
  spelling and sentence remain available in the entry's context.
- Counts track dictionary spellings rather than individual senses. Variant
  spellings group by their explicit simplified headword; alternate readings
  remain available. Existing saved entries are combined automatically on upgrade.
- Correcting a lookup replaces its contribution; it does not create another lookup.
- If recognition or a correction fails, **Edit text** remains available and
  keeps your draft for retrying. Previously saved vocabulary remains intact.
- Dismissed work that has not completed never saves or reopens a note.
- Search accepts Chinese, accented pinyin, or English. Select an entry to inspect
  its context; **Delete selected entry** removes that entry and its count.

Data lives in `%LOCALAPPDATA%\ChineseScreenDictionary`:

- `vocabulary.sqlite3`: vocabulary and lookup context
- `settings.json`: shortcuts and preferences
- `models`: model downloads and installed translation packages
- `cache`: language-library caches
- `app.log`: rotating error log

Screenshots are held in memory for the current lookup and are not saved or sent
to a service. There is no hosted backend, account, subscription, or API key.
Close the app before copying the data folder for a backup. The `CSD_DATA_DIR`
environment variable can select a separate data folder for testing.

## Limits

The app supports Windows 10/11 x64, multiple monitors, and differing display
scales. A selection is constrained to the monitor where the drag began. Protected
video, the UAC secure desktop, and content excluded from Windows screen capture
cannot be read. Select an individual speech bubble when possible; panel reading
order can be ambiguous. Mixed orientations in one selection, very decorative
lettering, names, and slang may need correction. Offline machine translation is
an aid, and can be inaccurate; dictionary meanings are displayed separately.

## Develop and test

Use Python **3.12** in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -e . --no-deps --no-build-isolation
.\.venv\Scripts\pythonw.exe -m chinese_screen_dictionary
```

Run unit, database, and Qt tests:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:\QT_QPA_PLATFORM
```

Run the real-model diagnostic against synthetic test images:

```powershell
$env:CSD_DATA_DIR = Join-Path (Get-Location) '.test-data'
.\.venv\Scripts\python.exe -m chinese_screen_dictionary --download-models
.\.venv\Scripts\python.exe -m chinese_screen_dictionary --self-test artifacts\source-check
```

The diagnostic blocks Python socket connections during OCR/translation, checks
both scripts and reading directions, records elapsed time and text, and renders
the popup and dictionary to PNG. It uses generated Chinese test images and does
not capture your screen. For executable parity, run the packaged executable with
the same `--self-test` option; inspect `report.json` and `app.log` for results.

Build the portable folder:

```powershell
.\.venv\Scripts\python.exe scripts\make_icon.py
.\.venv\Scripts\pyinstaller.exe --noconfirm ChineseScreenDictionary.spec
.\.venv\Scripts\python.exe scripts\prepare_release.py
```

The bundled asset manifest pins model URLs, byte sizes, and SHA-256 digests.
`scripts/fetch_assets.py` is a deliberate development-time refresh command, not
a runtime updater. Review its downloads and changes to the manifest before a
new release. The packaged app includes only the CPU inference engines used here.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for dictionary/model sources
and library attribution.

## Validation on this computer

On October 5, 2026, all **32 automated tests** passed, covering vocabulary counts,
correction rollback, restart persistence, reading order, selection masks, popup
placement, shortcut conflicts, cancelled results, ambiguous readings, and migration
of existing variant entries. Deliberately broken cancellation and migration
guards were rejected by their regression tests.

The portable executable passed **9 real-model checks** with Python socket
connections blocked: a character, a phrase, a sentence, multiline text,
traditional Chinese, vertical columns, a generated stylized speech bubble,
a blank image, and a repeated lookup. The popup and library renders were reviewed.
This does not constitute an accuracy benchmark on real webtoon pages.

An additional native Windows check exercised rectangle selection at 150% scaling
and lasso selection at 100% scaling on the two connected monitors. Both recognized
the displayed test sentence and placed the popup within the correct monitor.
Windows hotkey messages dismissed selection and processing; late results neither
reopened the note nor changed vocabulary counts. Re-run this check with
`python scripts/check_capture_flow.py` after closing the tray app.

For the sentence `我喜欢学习中文`, warm CPU recognition took **0.111 seconds** and
translation **0.033 seconds**; the traditional equivalent took **0.120** and
**0.034 seconds**. First use additionally loads the dictionary and engines:
the packaged cold diagnostic took about **12 seconds**, while later example
lookups generally took **0.1–0.6 seconds**. Larger or more complex selections
can take longer. Detailed local results are under `artifacts`.
