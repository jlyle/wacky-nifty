# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A self-hosted Flask + SQLite app for tracking a personal Wacky Packages sticker
collection: 488 cards across 16 series, plus a 16-series puzzle-back set (9
pieces/series). There is no ORM, no JS framework, and no test suite — the whole
backend is `app.py`, rendered through server-side Jinja templates.

## Commands

```bash
./run.sh                 # create venv, pip install flask, run app at http://localhost:5050
python3 app.py           # run directly if venv already set up (debug server, port 5050)
```

Desktop build (see README.md for full detail):

```bash
# Linux ONLY needs the system GTK/WebKit bindings visible, so recreate the venv with:
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements-desktop.txt
python3 desktop.py       # run the pywebview native-window shell
pyinstaller desktop.spec # bundle a standalone executable into dist/ (no cross-compile)
```

`.github/workflows/build-desktop.yml` builds Linux/Fedora/Windows/macOS
executables in parallel (manual trigger from the Actions tab).

## Architecture and conventions

**The database is committed to the repo.** `wacky_packages.db` is the source of
truth *and* tracked in git — editing your collection through the app produces a
diff in that binary file. Data changes and code changes travel together in
commits.

**Schema migrates itself at runtime, on every read.** There are no migration
files. `ensure_card_columns()` and `ensure_puzzle_table()` (`app.py`) run
`ALTER TABLE ... ADD COLUMN` / `CREATE TABLE IF NOT EXISTS` and seed puzzle rows
idempotently. `load_cards()` calls `ensure_card_columns()` every time, and read
queries defensively fall back to `NULL AS <col>` for columns that may not exist.
To add a card field: add it to the `wanted` dict in `ensure_card_columns()` and
to the `fields`/dict in `load_cards()` — do not write a migration.

**Filtering and sorting happen in Python, not SQL.** `load_cards()` pulls all
rows once; `apply_card_filters()` does search/series/ownership/back-color/sort in
memory. Export routes reuse the same `apply_card_filters()` so downloads respect
the current query string.

**Mutations are individual POST routes that redirect back.** Each field has its
own endpoint (`/mark_owned`, `/update_duplicates`, `/update_back_color`,
`/update_notes`, `/update_order_date`, `/update_puzzle_piece/...`). They all
redirect to `request.form["next"]` → `request.referrer` → a sensible default, so
the UI stays put after edits. No AJAX.

**Owned and duplicate_count are independent.** Setting a duplicate count does not
change `owned` — a card can have duplicates without being marked owned. Marking a
card missing (`/mark_missing`) still zeroes `duplicate_count`.

**DB path depends on whether it's frozen.** In dev, the DB is `BASE_DIR/wacky_packages.db`.
When packaged (`sys.frozen`), `app.py` copies the seed DB into a per-user, per-OS
data dir (`user_data_dir()`) on first launch so each user gets a private,
update-surviving copy. `desktop.py` imports `app`, runs Flask in a background
thread, and wraps it in a pywebview window.

**Display name formatting:** `format_name()` inserts a space between a digit and
a following letter (raw `sticker_name` values are run together). The stored
`sticker_name` is preserved; only the derived `name` is cleaned.

## Non-obvious files

- `dupes.txt`, `missing_cards.txt` — reference notes, not consumed by the app.
- `README.txt` — legacy install notes for an old patch drop, unrelated to current setup.
- `static/cards/` — card images referenced by the `image_filename`/`image` DB columns.
