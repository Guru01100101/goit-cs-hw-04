import threading
import time
from collections import defaultdict
from pathlib import Path

from postprocess import merge_results, print_errors, print_results
from preprocess import build_arg_parser, collect_files_or_exit, safe_search_in_file, split_into_chunks


def worker(files: list[Path], keywords: list[str], partials: list[dict], errors: list[str], lock: threading.Lock) -> None:
    """Потік обробляє свою частину файлів і додає свій результат у спільний список."""
    name = threading.current_thread().name
    partial: dict[str, list[str]] = defaultdict(list)
    local_errors: list[str] = []
    for path in files:
        found, error = safe_search_in_file(path, keywords, name)
        if error:
            local_errors.append(error)
        for kw in found:
            partial[kw].append(str(path))
    with lock:
        partials.append(partial)
        errors.extend(local_errors)


def search_threading(files: list[Path], keywords: list[str], num_threads: int = 4) -> dict[str, list[str]]:
    """Шукає ключові слова у файлах за допомогою кількох потоків.

    Повертає словник: ключ — ключове слово, значення — список шляхів до файлів.
    """
    if not files or not keywords:
        return {kw: [] for kw in keywords}

    partials: list[dict] = []
    errors: list[str] = []
    lock = threading.Lock()
    threads = [
        threading.Thread(target=worker, args=(chunk, keywords, partials, errors, lock), name=f"Thread-{i}")
        for i, chunk in enumerate(split_into_chunks(files, num_threads), start=1)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print_errors(errors)
    return merge_results(partials, keywords)


def main() -> None:
    args = build_arg_parser(
        "Багатопотоковий пошук ключових слів у файлах",
        "Кількість потоків (за замовчуванням 4)",
        4,
    ).parse_args()
    files = collect_files_or_exit(args.directory, args.pattern)
    print(f"Знайдено файлів: {len(files)}, потоків: {args.workers}")

    start = time.perf_counter()
    results = search_threading(files, args.keywords, args.workers)
    elapsed = time.perf_counter() - start

    print_results(results, elapsed, "threading")


if __name__ == "__main__":
    main()
