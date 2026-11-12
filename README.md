# goit-cs-hw-04

Homework GoIT University Computer Science.

Програма паралельно шукає ключові слова в текстових файлах. Є дві версії:

- **`search_thread.py`** — багатопотокова (`threading`);
- **`search_mproc.py`** — багатопроцесорна (`multiprocessing`, результати збираються через `Queue`).

Обидві версії ділять список файлів між потоками/процесами, вимірюють час виконання
і повертають словник `{ключове_слово: [шляхи до файлів, де його знайдено]}`.

## Вимоги

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (для встановлення залежностей і запуску тестів)

Сама програма використовує лише стандартну бібліотеку. Залежності потрібні тільки для тестів.

```
uv sync
```

## Використання

```
python search_thread.py <directory> <keyword> [<keyword> ...] [-n WORKERS] [-p PATTERN]
python search_mproc.py  <directory> <keyword> [<keyword> ...] [-n WORKERS] [-p PATTERN]
```

### Параметри

| Параметр | Обов'язковий | За замовчуванням | Опис |
|---|---|---|---|
| `directory` | так | — | Директорія з текстовими файлами. Пошук рекурсивний (включно з підпапками). Для пошуку в поточній папці вкажіть `.` |
| `keywords` | так | — | Одне або кілька ключових слів через пробіл. Фразу з пробілами беріть у лапки: `"hello world"`. |
| `-n`, `--workers` | ні | `search_thread.py`: **4** потоки<br>`search_mproc.py`: **кількість ядер CPU** | Кількість потоків / процесів. Якщо файлів менше, ніж воркерів, зайві не створюються. |
| `-p`, `--pattern` | ні | `*.txt` | Маска імен файлів (glob), наприклад `*.md` або `log_*.txt`. Беріть у лапки, щоб її не розгорнула оболонка. |
| `-h`, `--help` | ні | — | Показати довідку і вийти. |

### Як працює пошук

- Регістр **не враховується**: `python` знайде і `Python`, і `PYTHON`.
- Шукається **входження підрядка**: `python` знайде також `pythonic`.
- Файли читаються в кодуванні **UTF-8**.

### Приклади

Шукати два слова в усіх `.txt` у папці `data` з 4 потоками:

```
python search_thread.py data python queue
```

Шукати в поточній папці:

```
python search_thread.py . python queue
```

Шукати в папці `data` з 8 процесами:

```
python search_mproc.py data python queue -n 8
```

Шукати фразу в Markdown-файлах:

```
python search_thread.py docs "error handling" -p "*.md"
```

### Приклад виведення

```
Знайдено файлів: 4, потоків: 2

'python': 2 файл(ів)
  - data\a.txt
  - data\d.txt

'queue': 1 файл(ів)
  - data\b.txt

'missing': 0 файл(ів)

Час виконання (threading): 0.0079 с
```

### Обробка помилок

- Якщо директорії не існує, шлях не є директорією або до неї немає доступу, програма виводить помилку
  і завершується з кодом **1**.
- Якщо окремий файл не вдалося прочитати (немає доступу, не UTF-8, зник під час роботи тощо),
  програма виводить повідомлення в `stderr` із назвою потоку/процесу і **продовжує** обробку інших файлів.

## Використання як модуля

```python
from pathlib import Path

from search_mproc import search_multiprocessing
from search_thread import search_threading
from utils import collect_files

files = collect_files(Path("data"), "*.txt")

result = search_threading(files, ["python", "queue"], num_threads=4)
# {'python': ['data\\a.txt', 'data\\d.txt'], 'queue': ['data\\b.txt']}

if __name__ == "__main__":  # обов'язково для multiprocessing на Windows
    result = search_multiprocessing(files, ["python", "queue"], num_processes=4)
```

## Структура проєкту

```
search_thread.py   # версія з threading
search_mproc.py    # версія з multiprocessing
utils.py           # спільне: argparse, збір файлів, поділ на чанки, пошук у файлі, об'єднання та виведення результатів
tests/             # тести pytest з моками
```

## Тести

```
uv run python -m pytest -v
```

З перевіркою покриття (у колонці `Missing` — рядки, не покриті тестами):

```
uv run python -m pytest --cov
uv run python -m pytest --cov --cov-report=html   # HTML-звіт у htmlcov/index.html
```

> Якщо `uv run pytest` не запускається через політики безпеки Windows, використовуйте `python -m pytest`, як вище.
