import threading
from pathlib import Path

import pytest

import search_thread
from conftest import fake_safe_search


@pytest.fixture
def mock_search(mocker):
    return mocker.patch("search_thread.safe_search_in_file", side_effect=fake_safe_search)


@pytest.fixture
def mock_print_errors(mocker):
    return mocker.patch("search_thread.print_errors")


def test_worker_collects_results_and_errors(mock_search):
    partials, errors = [], []
    search_thread.worker([Path("a.txt"), Path("bad.txt"), Path("d.txt")], ["python", "queue"],
                         partials, errors, threading.Lock())

    assert mock_search.call_count == 3
    assert len(partials) == 1
    assert dict(partials[0]) == {"python": ["a.txt", "d.txt"], "queue": ["d.txt"]}
    assert len(errors) == 1


def test_search_threading_finds_keywords(files, mock_search, mock_print_errors):
    result = search_thread.search_threading(files + [Path("bad.txt")], ["python", "queue", "missing"], 2)

    assert result == {"python": ["a.txt", "d.txt"], "queue": ["b.txt", "d.txt"], "missing": []}
    errors = mock_print_errors.call_args.args[0]
    assert len(errors) == 1
    assert "помилка" in errors[0]


def test_files_are_distributed_between_threads(files, mocker, mock_search, mock_print_errors):
    mock_thread = mocker.patch("search_thread.threading.Thread", wraps=threading.Thread)

    search_thread.search_threading(files, ["python"], 3)

    assert mock_thread.call_count == 3
    chunks = [call.kwargs["args"][0] for call in mock_thread.call_args_list]
    assert [p for c in chunks for p in c] == files  # each file goes to exactly one thread
    assert mock_search.call_count == len(files)
    worker_names = {call.args[2] for call in mock_search.call_args_list}
    assert worker_names <= {"Thread-1", "Thread-2", "Thread-3"}


@pytest.mark.parametrize(
    ("file_list", "keywords", "expected"),
    [([], ["a"], {"a": []}), (None, [], {})],
    ids=["no-files", "no-keywords"],
)
def test_empty_input_starts_no_threads(files, mocker, file_list, keywords, expected):
    mock_thread = mocker.patch("search_thread.threading.Thread")
    assert search_thread.search_threading(files if file_list is None else file_list, keywords, 4) == expected
    mock_thread.assert_not_called()


def test_main_wires_everything(files, mocker, monkeypatch):
    mock_collect = mocker.patch("search_thread.collect_files_or_exit", return_value=files)
    mock_search = mocker.patch("search_thread.search_threading", return_value={"python": ["a.txt"]})
    mock_print_results = mocker.patch("search_thread.print_results")
    monkeypatch.setattr("sys.argv", ["search_thread.py", "python", "-d", "data", "-n", "2", "-p", "*.md"])

    search_thread.main()

    mock_collect.assert_called_once_with(Path("data"), "*.md")
    mock_search.assert_called_once_with(files, ["python"], 2)
    results, elapsed, label = mock_print_results.call_args.args
    assert results == {"python": ["a.txt"]}
    assert elapsed >= 0
    assert label == "threading"
