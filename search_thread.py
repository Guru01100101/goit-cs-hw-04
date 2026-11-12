"""Багатопотоковий пошук ключових слів у текстових файлах (threading)."""

import argparse
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path


def split_into_chunks(items: list, n: int) -> list[list]:
    """Розподіляє список на n майже рівних частин (порожні частини відкидаються)."""
    n = max(1, min(n, len(items)))
    k, m = divmod(len(items), n)
    return [items[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n)]


def search_in_file(path: Path, keywords: list[str]) -> set[str]:
    """Повертає множину ключових слів, знайдених у файлі (без урахування регістру)."""
    text = path.read_text(encoding="utf-8").lower()
    return {kw for kw in keywords if kw.lower() in text}


def worker(
    files: list[Path],
    keywords: list[str],
    results: dict[str, list[str]],
    errors: list[str],
    lock: threading.Lock,
) -> None:
    """Потік обробляє свою частину файлів і записує результати у спільний словник."""
    name = threading.current_thread().name
    for path in files:
        try:
            found = search_in_file(path, keywords)
        except FileNotFoundError:
            msg = f"[{name}] Файл не знайдено: {path}"
        except PermissionError:
            msg = f"[{name}] Немає доступу до файлу: {path}"
        except UnicodeDecodeError:
            msg = f"[{name}] Не вдалося декодувати файл (не UTF-8): {path}"
        except OSError as e:
            msg = f"[{name}] Помилка читання {path}: {e}"
        else:
            with lock:
                for kw in found:
                    results[kw].append(str(path))
            continue
        with lock:
            errors.append(msg)


def search_threading(
    files: list[Path], keywords: list[str], num_threads: int = 4
) -> dict[str, list[str]]:
    """Шукає ключові слова у файлах за допомогою кількох потоків.

    Повертає словник: ключ — ключове слово, значення — список шляхів до файлів.
    """
    results: dict[str, list[str]] = defaultdict(list)
    errors: list[str] = []
    if not files or not keywords:
        return {kw: [] for kw in keywords}

    lock = threading.Lock()
    threads = []
    for i, chunk in enumerate(split_into_chunks(files, num_threads), start=1):
        t = threading.Thread(
            target=worker,
            args=(chunk, keywords, results, errors, lock),
            name=f"Thread-{i}",
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    for msg in errors:
        print(msg, file=sys.stderr)

    return {kw: sorted(results.get(kw, [])) for kw in keywords}


def collect_files(directory: Path, pattern: str = "*.txt") -> list[Path]:
    """Збирає список текстових файлів у директорії (рекурсивно)."""
    if not directory.exists():
        raise FileNotFoundError(f"Директорія не існує: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"Шлях не є директорією: {directory}")
    return sorted(p for p in directory.rglob(pattern) if p.is_file())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Багатопотоковий пошук ключових слів у файлах")
    parser.add_argument("directory", type=Path, help="Директорія з текстовими файлами")
    parser.add_argument("keywords", nargs="+", help="Ключові слова для пошуку")
    parser.add_argument("-n", "--threads", type=int, default=4, help="Кількість потоків (за замовчуванням 4)")
    parser.add_argument("-p", "--pattern", default="*.txt", help="Маска файлів (за замовчуванням *.txt)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        files = collect_files(args.directory, args.pattern)
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        print(f"Помилка: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Знайдено файлів: {len(files)}, потоків: {args.threads}")

    start = time.perf_counter()
    results = search_threading(files, args.keywords, args.threads)
    elapsed = time.perf_counter() - start

    for kw, paths in results.items():
        print(f"\n'{kw}': {len(paths)} файл(ів)")
        for p in paths:
            print(f"  - {p}")
    print(f"\nЧас виконання (threading): {elapsed:.4f} с")


if __name__ == "__main__":
    main()
