import queue
from pathlib import Path

import pytest

import search_mproc
from conftest import fake_safe_search


class FakeProcess:
    """Stand-in for mp.Process: runs target synchronously in the current process.

    Real processes on Windows are started via spawn and don't see mocks,
    so Process is replaced for unit tests.
    """

    instances: list["FakeProcess"] = []

    def __init__(self, target, args, name):
        self.target, self.args, self.name = target, args, name
        FakeProcess.instances.append(self)

    def start(self):
        self.target(*self.args)

    def is_alive(self):
        return False

    def join(self):
        pass


class CrashingProcess(FakeProcess):
    """A process that "crashes" and puts nothing into the queue."""

    def start(self):
        pass


@pytest.fixture(autouse=True)
def reset_fake_processes():
    FakeProcess.instances = []


@pytest.fixture
def mock_search(mocker):
    return mocker.patch("search_mproc.safe_search_in_file", side_effect=fake_safe_search)


@pytest.fixture
def mock_print_errors(mocker):
    return mocker.patch("search_mproc.print_errors")


def test_worker_puts_results_into_queue(mocker, mock_search):
    q = mocker.MagicMock()
    search_mproc.worker([Path("a.txt"), Path("bad.txt"), Path("d.txt")], ["python", "queue"], q)

    q.put.assert_called_once()
    partial, errors = q.put.call_args.args[0]
    assert partial == {"python": ["a.txt", "d.txt"], "queue": ["d.txt"]}
    assert len(errors) == 1


def test_worker_always_puts_even_on_unexpected_error(mocker):
    mocker.patch("search_mproc.safe_search_in_file", side_effect=RuntimeError("boom"))
    q = mocker.MagicMock()

    search_mproc.worker([Path("a.txt")], ["python"], q)

    partial, errors = q.put.call_args.args[0]
    assert partial == {}
    assert "Неочікувана помилка" in errors[0]
    assert "boom" in errors[0]


def test_finds_keywords_and_distributes_files(files, mocker, mock_search, mock_print_errors):
    mocker.patch("search_mproc.mp.Process", FakeProcess)
    all_files = files + [Path("bad.txt")]

    result = search_mproc.search_multiprocessing(all_files, ["python", "queue", "missing"], 3)

    assert result == {"python": ["a.txt", "d.txt"], "queue": ["b.txt", "d.txt"], "missing": []}
    assert len(FakeProcess.instances) == 3
    assert [f for p in FakeProcess.instances for f in p.args[0]] == all_files
    assert len(mock_print_errors.call_args.args[0]) == 1


def test_crashed_process_does_not_hang(files, mocker, mock_print_errors):
    mocker.patch("search_mproc.mp.Process", CrashingProcess)
    fake_queue = mocker.MagicMock()
    fake_queue.get.side_effect = queue.Empty
    fake_queue.empty.return_value = True
    mocker.patch("search_mproc.mp.Queue", return_value=fake_queue)

    result = search_mproc.search_multiprocessing(files, ["python"], 2)

    assert result == {"python": []}
    assert "Деякі процеси завершились без результату" in mock_print_errors.call_args.args[0]


def test_waits_while_processes_are_still_running(files, mocker, mock_print_errors):
    """The queue is temporarily empty but the process is alive: keep waiting instead of exiting."""
    slow_process = mocker.MagicMock()
    slow_process.is_alive.return_value = True
    mocker.patch("search_mproc.mp.Process", return_value=slow_process)
    fake_queue = mocker.MagicMock()
    fake_queue.get.side_effect = [queue.Empty, ({"python": ["a.txt"]}, [])]
    mocker.patch("search_mproc.mp.Queue", return_value=fake_queue)

    result = search_mproc.search_multiprocessing(files, ["python"], 1)

    assert result == {"python": ["a.txt"]}
    assert fake_queue.get.call_count == 2
    assert mock_print_errors.call_args.args[0] == []


def test_empty_input_starts_no_processes(mocker):
    mock_process = mocker.patch("search_mproc.mp.Process")
    assert search_mproc.search_multiprocessing([], ["a"], 4) == {"a": []}
    mock_process.assert_not_called()


def test_real_processes_with_temp_files(tmp_path, mock_print_errors):
    """Integration test with real processes and files."""
    (tmp_path / "a.txt").write_text("Python here", encoding="utf-8")
    (tmp_path / "b.txt").write_text("a Queue", encoding="utf-8")
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe\x00")
    files = sorted(tmp_path.glob("*.txt"))

    result = search_mproc.search_multiprocessing(files, ["python", "queue"], 2)

    assert result == {"python": [str(tmp_path / "a.txt")], "queue": [str(tmp_path / "b.txt")]}
    errors = mock_print_errors.call_args.args[0]
    assert len(errors) == 1
    assert "не UTF-8" in errors[0]


def test_main_defaults_to_cpu_count(files, mocker, monkeypatch):
    mocker.patch("search_mproc.mp.cpu_count", return_value=8)
    mock_collect = mocker.patch("search_mproc.collect_files_or_exit", return_value=files)
    mock_search = mocker.patch("search_mproc.search_multiprocessing", return_value={"python": []})
    mock_print_results = mocker.patch("search_mproc.print_results")
    monkeypatch.setattr("sys.argv", ["search_mproc.py", "python"])

    search_mproc.main()

    mock_collect.assert_called_once_with(Path("."), "*.txt")  # current directory by default
    mock_search.assert_called_once_with(files, ["python"], 8)
    assert mock_print_results.call_args.args[2] == "multiprocessing"
