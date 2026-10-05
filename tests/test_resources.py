import zipfile

import pytest

from chinese_screen_dictionary.resources import safe_extract


def test_model_archive_cannot_escape_destination(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../outside.txt", "bad")
    with pytest.raises(ValueError):
        safe_extract(archive, tmp_path / "model")
    assert not (tmp_path / "outside.txt").exists()
