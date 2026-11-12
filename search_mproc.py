"""Багатопроцесорний пошук ключових слів у текстових файлах (multiprocessing)."""

import argparse
import multiprocessing as mp
import queue
import sys
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
            try:
                found = search_in_file(path, keywords)
            except FileNotFoundError:
                errors.append(f"[{name}] Файл не знайдено: {path}")
            except PermissionError:
                errors.append(f"[{name}] Немає доступу до файлу: {path}")
            except UnicodeDecodeError:
                errors.append(f"[{name}] Не вдалося декодувати файл (не UTF-8): {path}")
            except OSError as e:
                errors.append(f"[{name}] Помилка читання {path}: {e}")
            else:
                for kw in found:
                    partial[kw].append(str(path))
    except Exception as e:  # гарантуємо, що процес завжди щось поверне в чергу
        errors.append(f"[{name}] Неочікувана помилка: {e!r}")
    finally:
        result_queue.put((dict(partial), errors))


def search_multiprocessing(
    files: list[Path], keywords: list[str], num_processes: int | None = None
) -> dict[str, list[str]]:
    """Шукає ключові слова у файлах за допомогою кількох процесів.

    Повертає словник: ключ — ключове слово, значення — список шляхів до файлів.
    """
    if not files or not keywords:
        return {kw: [] for kw in keywords}

    num_processes = num_processes or mp.cpu_count()
    chunks = split_into_chunks(files, num_processes)
    result_queue: mp.Queue = mp.Queue()

    processes = []
    for i, chunk in enumerate(chunks, start=1):
        p = mp.Process(target=worker, args=(chunk, keywords, result_queue), name=f"Process-{i}")
        processes.append(p)
        p.start()

    # Спочатку забираємо результати з черги, потім join — інакше можливий deadlock
    results: dict[str, list[str]] = defaultdict(list)
    errors: list[str] = []
    received = 0
    while received < len(processes):
        try:
            partial, errs = result_queue.get(timeout=1)
        except queue.Empty:
            # Якщо всі процеси вже завершились, а даних немає — якийсь процес аварійно впав
            if not any(p.is_alive() for p in processes) and result_queue.empty():
                errors.append("Деякі процеси завершились без результату")
                break
            continue
        received += 1
        errors.extend(errs)
        for kw, paths in partial.items():
            results[kw].extend(paths)

    for p in processes:
        p.join()

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
    parser = argparse.ArgumentParser(description="Багатопроцесорний пошук ключових слів у файлах")
    parser.add_argument("directory", type=Path, help="Директорія з текстовими файлами")
    parser.add_argument("keywords", nargs="+", help="Ключові слова для пошуку")
    parser.add_argument("-n", "--processes", type=int, default=None,
                        help="Кількість процесів (за замовчуванням — кількість ядер CPU)")
    parser.add_argument("-p", "--pattern", default="*.txt", help="Маска файлів (за замовчуванням *.txt)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        files = collect_files(args.directory, args.pattern)
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        print(f"Помилка: {e}", file=sys.stderr)
        sys.exit(1)

    num_processes = args.processes or mp.cpu_count()
    print(f"Знайдено файлів: {len(files)}, процесів: {num_processes}")

    start = time.perf_counter()
    results = search_multiprocessing(files, args.keywords, num_processes)
    elapsed = time.perf_counter() - start

    for kw, paths in results.items():
        print(f"\n'{kw}': {len(paths)} файл(ів)")
        for p in paths:
            print(f"  - {p}")
    print(f"\nЧас виконання (multiprocessing): {elapsed:.4f} с")


if __name__ == "__main__":
    main()
