import sys
from collections import defaultdict
from collections.abc import Iterable


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
