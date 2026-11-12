from pathlib import Path

import pytest

import utils


# ---------- build_arg_parser ----------

@pytest.fixture
def parser():
    return utils.build_arg_parser("test", "workers", 4)


def test_parser_defaults(parser):
    args = utils.parse_cli_args(parser, ["python"])
    assert args.keywords == ["python"]
    assert args.directory == Path(".")
    assert args.workers == 4
    assert args.pattern == "*.txt"


@pytest.mark.parametrize("flag", ["-d", "--dir"])
@pytest.mark.parametrize("value", [".", "..", "data/sub", "../other", "/abs/path"])
def test_parser_accepts_relative_and_absolute_dirs(parser, flag, value):
    assert utils.parse_cli_args(parser, ["python", flag, value]).directory == Path(value)


def test_parser_options_before_keywords(parser):
    args = utils.parse_cli_args(parser, ["-d", "..", "-n", "2", "-p", "*.md", "python"])
    assert (args.directory, args.workers, args.pattern, args.keywords) == (Path(".."), 2, "*.md", ["python"])


def test_parser_options_between_phrase_words(parser):
    args = utils.parse_cli_args(parser, ["hello", "-d", "..", "world", "-n", "2"])
    assert args.keywords == ["hello world"]
    assert (args.directory, args.workers) == (Path(".."), 2)


def test_no_args_prints_help_and_exits_0(parser, capsys):
    with pytest.raises(SystemExit) as exc_info:
        utils.parse_cli_args(parser, [])
    assert exc_info.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_no_args_reads_sys_argv(parser, monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "hello", "world"])
    assert utils.parse_cli_args(parser).keywords == ["hello world"]


@pytest.mark.parametrize("argv", [["-d", "."], ["", "  "]], ids=["only-options", "blank-keywords"])
def test_options_without_keywords_is_error(parser, argv, capsys):
    with pytest.raises(SystemExit) as exc_info:
        utils.parse_cli_args(parser, argv)
    assert exc_info.value.code == 2
    assert "не вказано жодного ключового слова" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (["python"], ["python"]),
        (["hello", "world"], ["hello world"]),  # no quotes -> one phrase
        (["hello world"], ["hello world"]),
        (["hello world", "foo bar"], ["hello world", "foo bar"]),  # each phrase quoted
        (["hello world", "python"], ["hello world", "python"]),
        (["python", "queue"], ["python queue"]),  # quotes around a single word are invisible
        ([" hello world ", "", "python"], ["hello world", "python"]),  # surrounding spaces, empty tokens
        (["hello world", "python", "hello world"], ["hello world", "python"]),  # duplicates
        ([], []),
    ],
    ids=["one-word", "words-join", "one-quoted", "two-quoted", "quoted-and-word",
         "single-words-join", "strip-and-empty", "duplicates", "empty"],
)
def test_parse_keywords(tokens, expected):
    assert utils.parse_keywords(tokens) == expected


def test_help_describes_phrases(parser):
    help_text = parser.format_help()
    assert "-d, --dir DIR" in help_text
    assert 'шукає "hello world" і "foo bar"' in help_text


@pytest.mark.parametrize(("cwd", "directory"), [("root", "."), ("root/sub", "..")])
def test_collect_files_with_relative_dirs(tmp_path, monkeypatch, cwd, directory):
    """'.' and '..' are resolved relative to the current working directory."""
    (tmp_path / "root" / "sub").mkdir(parents=True)
    (tmp_path / "root" / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "root" / "sub" / "b.txt").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path / cwd)

    found = utils.collect_files(Path(directory))

    assert sorted(p.resolve() for p in found) == [tmp_path / "root" / "a.txt", tmp_path / "root" / "sub" / "b.txt"]


# ---------- split_into_chunks ----------

@pytest.mark.parametrize(
    ("items", "n", "expected"),
    [
        ([1, 2, 3, 4], 2, [[1, 2], [3, 4]]),
        ([1, 2, 3, 4, 5], 3, [[1, 2], [3, 4], [5]]),
        ([1, 2], 5, [[1], [2]]),
        ([1, 2, 3], 0, [[1, 2, 3]]),
    ],
    ids=["even", "uneven", "more-chunks-than-items", "non-positive-n"],
)
def test_split_into_chunks(items, n, expected):
    assert utils.split_into_chunks(items, n) == expected


def test_split_preserves_all_items():
    items = list(range(17))
    chunks = utils.split_into_chunks(items, 4)
    assert [x for c in chunks for x in c] == items


# ---------- collect_files ----------

@pytest.fixture
def directory(mocker):
    d = mocker.MagicMock(spec=Path)
    d.exists.return_value = True
    d.is_dir.return_value = True
    return d


def test_collect_files_missing_directory(directory):
    directory.exists.return_value = False
    with pytest.raises(FileNotFoundError):
        utils.collect_files(directory)


def test_collect_files_not_a_directory(directory):
    directory.is_dir.return_value = False
    with pytest.raises(NotADirectoryError):
        utils.collect_files(directory)


def test_collect_files_returns_only_files_sorted(directory, mocker):
    a, b, sub = Path("a.txt"), Path("b.txt"), Path("subdir.txt")
    directory.rglob.return_value = [b, sub, a]
    mocker.patch.object(Path, "is_file", autospec=True, side_effect=lambda p: p != sub)

    assert utils.collect_files(directory, "*.txt") == [a, b]
    directory.rglob.assert_called_once_with("*.txt")


def test_collect_files_or_exit_exits_with_code_1(mocker, capsys):
    mocker.patch("utils.collect_files", side_effect=PermissionError("доступ заборонено"))

    with pytest.raises(SystemExit) as exc_info:
        utils.collect_files_or_exit(Path("dir"))

    assert exc_info.value.code == 1
    assert "доступ заборонено" in capsys.readouterr().err


def test_collect_files_or_exit_returns_files(mocker):
    mocker.patch("utils.collect_files", return_value=[Path("a.txt")])
    assert utils.collect_files_or_exit(Path("dir")) == [Path("a.txt")]


# ---------- search_in_file / safe_search_in_file ----------

def test_search_in_file_case_insensitive(make_path):
    path = make_path(text="Hello PYTHON world")
    assert utils.search_in_file(path, ["python", "World", "java"]) == {"python", "World"}
    path.read_text.assert_called_once_with(encoding="utf-8")


def test_safe_search_success(make_path):
    assert utils.safe_search_in_file(make_path(text="queue"), ["queue"], "W-1") == ({"queue"}, None)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (FileNotFoundError(), "Файл не знайдено"),
        (PermissionError(), "Немає доступу"),
        (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"), "не UTF-8"),
        (IsADirectoryError("is a dir"), "Помилка читання"),
    ],
    ids=["not-found", "permission", "decode", "other-oserror"],
)
def test_safe_search_handles_errors(make_path, error, expected):
    found, message = utils.safe_search_in_file(make_path("bad.txt", error=error), ["x"], "W-1")

    assert found == set()
    assert expected in message
    assert "[W-1]" in message
    assert "bad.txt" in message


def test_safe_search_does_not_swallow_other_exceptions(make_path):
    with pytest.raises(ValueError):
        utils.safe_search_in_file(make_path(error=ValueError()), ["x"], "W-1")


# ---------- merge / print ----------

def test_merge_results():
    partials = [{"a": ["2.txt"]}, {"a": ["1.txt"], "b": ["3.txt"]}, {}]
    assert utils.merge_results(partials, ["a", "b", "c"]) == {"a": ["1.txt", "2.txt"], "b": ["3.txt"], "c": []}


def test_merge_ignores_unknown_keywords():
    assert utils.merge_results([{"x": ["1.txt"]}], ["a"]) == {"a": []}


def test_print_errors_goes_to_stderr(capsys):
    utils.print_errors(["e1", "e2"])
    captured = capsys.readouterr()
    assert captured.err == "e1\ne2\n"
    assert captured.out == ""


def test_print_results(capsys):
    utils.print_results({"a": ["1.txt"], "b": []}, 0.12345, "test")
    out = capsys.readouterr().out

    assert "'a': 1 файл(ів)" in out
    assert "  - 1.txt" in out
    assert "'b': 0 файл(ів)" in out
    assert "Час виконання (test): 0.1235 с" in out
