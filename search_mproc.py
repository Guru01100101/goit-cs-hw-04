import multiprocessing as mp
import queue
import time
from collections import defaultdict
from pathlib import Path

from utils import (
    build_arg_parser,
    collect_files_or_exit,
    merge_results,
    parse_cli_args,
    print_errors,
    print_results,
    safe_search_in_file,
    split_into_chunks,
)


def worker(files: list[Path], keywords: list[str], result_queue: mp.Queue) -> None:
    """Process worker: process its chunk of files and send the result to the queue.

    Puts a tuple (partial_results, errors) into the queue, where
    partial_results is a dict {keyword: [paths]}.
    """
    name = mp.current_process().name
    partial: dict[str, list[str]] = defaultdict(list)
    errors: list[str] = []
    try:
        for path in files:
            found, error = safe_search_in_file(path, keywords, name)
            if error:
                errors.append(error)
            for kw in found:
                partial[kw].append(str(path))
    except Exception as e:  # make sure the process always puts something into the queue
        errors.append(f"[{name}] Неочікувана помилка: {e!r}")
    finally:
        result_queue.put((dict(partial), errors))


def search_multiprocessing(files: list[Path], keywords: list[str], num_processes: int | None = None) -> dict[str, list[str]]:
    """Search files for keywords using multiple processes.

    Return a dict: key is a keyword, value is a list of file paths where it was found.
    """
    if not files or not keywords:
        return {kw: [] for kw in keywords}

    num_processes = num_processes or mp.cpu_count()
    result_queue: mp.Queue = mp.Queue()
    processes = [
        mp.Process(target=worker, args=(chunk, keywords, result_queue), name=f"Process-{i}")
        for i, chunk in enumerate(split_into_chunks(files, num_processes), start=1)
    ]
    for p in processes:
        p.start()

    # Drain the queue first, then join; otherwise a deadlock is possible
    partials: list[dict] = []
    errors: list[str] = []
    while len(partials) < len(processes):
        try:
            partial, errs = result_queue.get(timeout=1)
        except queue.Empty:
            # All processes have exited but no data arrived: some process crashed
            if not any(p.is_alive() for p in processes) and result_queue.empty():
                errors.append("Деякі процеси завершились без результату")
                break
            continue
        partials.append(partial)
        errors.extend(errs)

    for p in processes:
        p.join()

    print_errors(errors)
    return merge_results(partials, keywords)


def main() -> None:
    args = parse_cli_args(build_arg_parser(
        "Багатопроцесорний пошук ключових слів у файлах",
        "Кількість процесів (за замовчуванням — кількість ядер CPU)",
        None,
    ))
    files = collect_files_or_exit(args.directory, args.pattern)
    num_processes = args.workers or mp.cpu_count()
    print(f"Знайдено файлів: {len(files)}, процесів: {num_processes}")

    start = time.perf_counter()
    results = search_multiprocessing(files, args.keywords, num_processes)
    elapsed = time.perf_counter() - start

    print_results(results, elapsed, "multiprocessing")


if __name__ == "__main__":
    main()
