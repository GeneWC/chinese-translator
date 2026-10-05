# Third-party notices

Chinese Screen Dictionary uses the following projects. Their respective licenses
apply to their code and data; the dictionary is separate from the application code.

- **CC-CEDICT**, MDBG and contributors. The included, unmodified dictionary
  snapshot is distributed under **Creative Commons Attribution-ShareAlike 4.0**.
  Its copyright and licensing header is preserved inside `cedict.txt.gz`.
  Source: https://www.mdbg.net/chinese/dictionary?page=cedict
  License: https://creativecommons.org/licenses/by-sa/4.0/
  Snapshot SHA-256 is recorded in the bundled `dictionary.json`.
- **RapidOCR**, RapidAI contributors, Apache-2.0.
  https://github.com/RapidAI/RapidOCR
- **PaddleOCR PP-OCRv5 and orientation model**, PaddlePaddle contributors,
  Apache-2.0. The ONNX conversions are distributed by RapidAI.
  https://github.com/PaddlePaddle/PaddleOCR
  https://www.modelscope.cn/models/RapidAI/RapidOCR
- **Argos Translate**, Argos Open Technologies and contributors, MIT / CC0.
  https://github.com/argosopentech/argos-translate
  The Chinese-to-English 1.9 language packages are downloaded from the project's
  package index. Their package metadata and packaged license files are retained
  in the installed model directories.
  https://github.com/argosopentech/argospm-index
- **CTranslate2**, OpenNMT contributors, MIT.
  https://github.com/OpenNMT/CTranslate2
- **ONNX Runtime**, Microsoft and contributors, MIT.
  https://github.com/microsoft/onnxruntime
- **PySide6 / Qt for Python**, The Qt Company and contributors,
  LGPL-3.0/GPL/commercial licensing as applicable. The portable build uses
  dynamically linked Qt libraries under the open-source distribution terms.
  The `_internal` folder contains the replaceable libraries; no restriction is
  imposed by this app on debugging modifications to those libraries.
  https://www.qt.io/qt-for-python
  https://code.qt.io/cgit/pyside/pyside-setup.git/
  https://code.qt.io/cgit/qt/qtbase.git/
  https://www.gnu.org/licenses/lgpl-3.0.html
- **jieba**, Sun Junyi and contributors, MIT.
  https://github.com/fxsjy/jieba
- **pypinyin**, mozillazg and contributors, MIT.
  https://github.com/mozillazg/python-pinyin
- **SentencePiece**, Google and contributors, Apache-2.0.
  https://github.com/google/sentencepiece
- Other dependencies include NumPy, OpenCV, Pillow, Shapely, pyclipper,
  Requests, PyYAML, and OmegaConf. Distribution license files are copied
  into `licenses` in the portable app folder by the release preparation script.

The popup takes inspiration from Zhongwen's character/pinyin/definition layout;
this app does not include Zhongwen extension code or assets.
