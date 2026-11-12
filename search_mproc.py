import multiprocessing as mp
import queue
import time
from collections import defaultdict
from pathlib import Path

from postprocess import merge_results, print_errors, print_results
from preprocess import build_arg_parser, collect_files_or_exit, safe_search_in_file, split_into_chunks


def worker(files: list[Path], keywords: list[str], result_queue: mp.Queue) -> None:
    """Процес обробляє свою частину файлів і надсилає результат у чергу.

    У чергу кладеться кортеж (partial_results, errors), де
    partial_results — словник {ключове_слово: [шляхи]}.
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
    except Exception as e:  # гарантуємо, що процес завжди щось поверне в чергу
        errors.append(f"[{name}] Неочікувана помилка: {e!r}")
    finally:
        result_queue.put((dict(partial), errors))


def search_multiprocessing(files: list[Path], keywords: list[str], num_processes: int | None = None) -> dict[str, list[str]]:
    """Шукає ключові слова у файлах за допомогою кількох процесів.

    Повертає словник: ключ — ключове слово, значення — список шляхів до файлів.
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

    # Спочатку забираємо результати з черги, потім join — інакше можливий deadlock
    partials: list[dict] = []
    errors: list[str] = []
    while len(partials) < len(processes):
        try:
            partial, errs = result_queue.get(timeout=1)
        except queue.Empty:
            # Якщо всі процеси вже завершились, а даних немає — якийсь процес аварійно впав
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
    args = build_arg_parser(
        "Багатопроцесорний пошук ключових слів у файлах",
        "Кількість процесів (за замовчуванням — кількість ядер CPU)",
        None,
    ).parse_args()
    files = collect_files_or_exit(args.directory, args.pattern)
    num_processes = args.workers or mp.cpu_count()
    print(f"Знайдено файлів: {len(files)}, процесів: {num_processes}")

    start = time.perf_counter()
    results = search_multiprocessing(files, args.keywords, num_processes)
    elapsed = time.perf_counter() - start

    print_results(results, elapsed, "multiprocessing")


if __name__ == "__main__":
    main()
