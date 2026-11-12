import argparse
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path


KEYWORDS_EPILOG = """\
Як задавати запити:
  Слова без лапок склеюються в ОДНУ фразу:
    %(prog)s hello world                 -> шукає "hello world"
  Кожна фраза в лапках — окремий запит:
    %(prog)s "hello world" "foo bar"     -> шукає "hello world" і "foo bar"
    %(prog)s "hello world" python        -> шукає "hello world" і "python"
  Обмеження: лапки навколо одного слова оболонка прибирає, тому
    %(prog)s "python" "queue"            -> шукає одну фразу "python queue"
  Принаймні один запит має містити пробіл, щоб запити розділялися.

Приклади:
  %(prog)s python                        пошук у поточній директорії
  %(prog)s python -d ..                  пошук у батьківській директорії
  %(prog)s error handling -d docs -p "*.md" -n 2
"""


def build_arg_parser(description: str, workers_help: str, workers_default: int | None) -> argparse.ArgumentParser:
    """Створює парсер аргументів командного рядка, спільний для обох версій."""
    parser = argparse.ArgumentParser(
        description=description,
        epilog=KEYWORDS_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "keywords", nargs="*", metavar="keyword",
        help="Фраза для пошуку. Слова без лапок — одна фраза; кілька фраз — кожну в лапках (див. нижче)",
    )
    parser.add_argument(
        "-d", "--dir", dest="directory", metavar="DIR", type=Path, default=Path("."),
        help="Директорія з текстовими файлами: абсолютний або відносний шлях, напр. . чи .. "
             "(за замовчуванням поточна директорія)",
    )
    parser.add_argument("-n", "--workers", type=int, default=workers_default, help=workers_help)
    parser.add_argument("-p", "--pattern", default="*.txt", help="Маска файлів (за замовчуванням *.txt)")
    return parser


def parse_keywords(tokens: list[str]) -> list[str]:
    """Перетворює позиційні аргументи на список запитів.

    Оболонка прибирає лапки, тому фрази в лапках видно лише за пробілом усередині аргументу:
    - жоден аргумент не містить пробілу -> усі слова склеюються в одну фразу;
    - є аргумент із пробілом -> кожен аргумент є окремим запитом.
    Порожні запити й дублікати відкидаються, порядок зберігається.
    """
    tokens = [t.strip() for t in tokens]
    if not any(" " in t for t in tokens):
        tokens = [" ".join(t for t in tokens if t)]
    return list(dict.fromkeys(t for t in tokens if t))


def parse_cli_args(parser: argparse.ArgumentParser, argv: list[str] | None = None) -> argparse.Namespace:
    """Розбирає аргументи командного рядка.

    Без аргументів виводить довідку і завершує програму. Опції можна змішувати зі словами фрази.
    """
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        parser.print_help()
        sys.exit(0)
    args = parser.parse_intermixed_args(argv)
    args.keywords = parse_keywords(args.keywords)
    if not args.keywords:
        parser.error("не вказано жодного ключового слова")
    return args


def collect_files(directory: Path, pattern: str = "*.txt") -> list[Path]:
    """Збирає список текстових файлів у директорії (рекурсивно)."""
    if not directory.exists():
        raise FileNotFoundError(f"Директорія не існує: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Шлях не є директорією: {directory}")
    return sorted(p for p in directory.rglob(pattern) if p.is_file())


def collect_files_or_exit(directory: Path, pattern: str = "*.txt") -> list[Path]:
    """Те саме, що collect_files, але при помилці виводить повідомлення і завершує програму."""
    try:
        return collect_files(directory, pattern)
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        print(f"Помилка: {e}", file=sys.stderr)
        sys.exit(1)


def split_into_chunks(items: list, n: int) -> list[list]:
    """Розподіляє список на n майже рівних частин (порожні частини відкидаються)."""
    n = max(1, min(n, len(items)))
    k, m = divmod(len(items), n)
    return [items[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n)]


def search_in_file(path: Path, keywords: list[str]) -> set[str]:
    """Повертає множину ключових слів, знайдених у файлі (без урахування регістру)."""
    text = path.read_text(encoding="utf-8").lower()
    return {kw for kw in keywords if kw.lower() in text}


def safe_search_in_file(path: Path, keywords: list[str], worker_name: str) -> tuple[set[str], str | None]:
    """Шукає ключові слова у файлі, перехоплюючи помилки файлової системи.

    Повертає (знайдені_слова, повідомлення_про_помилку або None).
    """
    try:
        return search_in_file(path, keywords), None
    except FileNotFoundError:
        msg = f"Файл не знайдено: {path}"
    except PermissionError:
        msg = f"Немає доступу до файлу: {path}"
    except UnicodeDecodeError:
        msg = f"Не вдалося декодувати файл (не UTF-8): {path}"
    except OSError as e:
        msg = f"Помилка читання {path}: {e}"
    return set(), f"[{worker_name}] {msg}"


def merge_results(partials: Iterable[dict[str, list[str]]], keywords: list[str]) -> dict[str, list[str]]:
    """Об'єднує часткові результати в один словник {ключове_слово: [шляхи]}.

    Кожне ключове слово присутнє в результаті (навіть якщо не знайдене), шляхи відсортовані.
    """
    merged: dict[str, list[str]] = defaultdict(list)
    for partial in partials:
        for kw, paths in partial.items():
            merged[kw].extend(paths)
    return {kw: sorted(merged.get(kw, [])) for kw in keywords}


def print_errors(errors: Iterable[str]) -> None:
    """Виводить повідомлення про помилки у stderr."""
    for msg in errors:
        print(msg, file=sys.stderr)


def print_results(results: dict[str, list[str]], elapsed: float, label: str) -> None:
    """Виводить результати пошуку та час виконання."""
    for kw, paths in results.items():
        print(f"\n'{kw}': {len(paths)} файл(ів)")
        for p in paths:
            print(f"  - {p}")
    print(f"\nЧас виконання ({label}): {elapsed:.4f} с")
