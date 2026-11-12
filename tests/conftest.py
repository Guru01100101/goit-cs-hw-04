from pathlib import Path

import pytest

FILE_CONTENTS = {
    "a.txt": {"python"},
    "b.txt": {"queue"},
    "c.txt": set(),
    "d.txt": {"python", "queue"},
}


def fake_safe_search(path, keywords, worker_name):
    """Замінник safe_search_in_file: результат беремо зі словника, bad.txt — помилка."""
    if path.name == "bad.txt":
        return set(), f"[{worker_name}] помилка"
    return FILE_CONTENTS[path.name] & set(keywords), None


@pytest.fixture
def files() -> list[Path]:
    return [Path(name) for name in FILE_CONTENTS]


@pytest.fixture
def make_path(mocker):
    """Фабрика моків шляху до файлу: read_text повертає text або кидає error."""

    def _make(name: str = "file.txt", text: str = "", error: Exception | None = None):
        path = mocker.MagicMock(spec=Path)
        path.__str__.return_value = name
        if error is not None:
            path.read_text.side_effect = error
        else:
            path.read_text.return_value = text
        return path

    return _make
