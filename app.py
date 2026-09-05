from flask import Flask, render_template, request, redirect, url_for, flash, Response
from dotenv import load_dotenv
import sqlite3, re, csv, io, os, shutil, sys, json
from pathlib import Path

app = Flask(__name__)
app.secret_key = "wacky-value-box"

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from services.research_db import ensure_research_tables, utcnow
from services.research_scanner import run_research_scan
from services.research_scheduler import start_scheduler, reschedule, status as scheduler_status
BACK_COLOR_OPTIONS = ["white", "tan", "red ludlow", "black ludlow", "cloth"]
PUZZLE_PIECES_PER_SERIES = 9
PUZZLE_COLUMN_LABELS = ["left", "middle", "right"]

def puzzle_piece_location(piece_number):
    row = (piece_number - 1) // 3 + 1
    column = PUZZLE_COLUMN_LABELS[(piece_number - 1) % 3]
    return row, column

def user_data_dir():
    """Writable per-OS location for the db when running as a packaged desktop app."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    data_dir = base / "WackyPackagesVault"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

if getattr(sys, "frozen", False):
    DB_PATH = user_data_dir() / "wacky_packages.db"
    if not DB_PATH.exists():
        seed_db = BASE_DIR / "wacky_packages.db"
        if seed_db.exists():
            shutil.copy(seed_db, DB_PATH)
else:
    DB_PATH = BASE_DIR / "wacky_packages.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

def table_columns(conn, table_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}

def ensure_card_columns():
    conn = get_db()
    cols = table_columns(conn, "cards")
    wanted = {
        "back_color": "TEXT",
        "image_filename": "TEXT",
        "image": "TEXT",
        "duplicate_count": "INTEGER DEFAULT 0",
        "owned": "INTEGER DEFAULT 0",
        "notes": "TEXT",
        "order_date": "TEXT",
    }
    for col, col_type in wanted.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE cards ADD COLUMN {col} {col_type}")
    conn.execute("UPDATE cards SET duplicate_count = 0 WHERE duplicate_count IS NULL")
    if "cond" in cols:
        conn.execute("ALTER TABLE cards DROP COLUMN cond")
    conn.commit()
    conn.close()

def ensure_research_schema():
    conn = get_db()
    ensure_research_tables(conn)
    conn.close()

def ensure_puzzle_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS series_puzzle_pieces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series INTEGER NOT NULL,
            piece_number INTEGER NOT NULL,
            owned INTEGER DEFAULT 0,
            duplicate_count INTEGER DEFAULT 0,
            notes TEXT,
            UNIQUE(series, piece_number)
        )
    """)
    cols = table_columns(conn, "series_puzzle_pieces")
    if "duplicate_count" not in cols:
        conn.execute("ALTER TABLE series_puzzle_pieces ADD COLUMN duplicate_count INTEGER DEFAULT 0")
    conn.execute("UPDATE series_puzzle_pieces SET duplicate_count = 0 WHERE duplicate_count IS NULL")
    for series in range(1, 17):
        for piece in range(1, PUZZLE_PIECES_PER_SERIES + 1):
            conn.execute("""
                INSERT OR IGNORE INTO series_puzzle_pieces (series, piece_number, owned, duplicate_count, notes)
                VALUES (?, ?, 0, 0, '')
            """, (series, piece))
    conn.commit()
    conn.close()

def normalize_owned(value):
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if int(value) == 1 else 0
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "owned"} else 0

def format_name(name):
    name = name or ""
    name = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", name)
    return name.strip()

def display_name(series, sticker_number, sticker_name):
    return format_name(sticker_name)

def get_image_value(row, columns):
    if "image_filename" in columns and row["image_filename"]:
        return row["image_filename"]
    if "image" in columns and row["image"]:
        return row["image"]
    return None

def load_cards():
    ensure_card_columns()
    conn = get_db()
    cols = table_columns(conn, "cards")
    fields = [
        "id", "series", "sticker_number", "sticker_name", "owned",
        "back_color" if "back_color" in cols else "NULL AS back_color",
        "image_filename" if "image_filename" in cols else "NULL AS image_filename",
        "image" if "image" in cols else "NULL AS image",
        "duplicate_count" if "duplicate_count" in cols else "0 AS duplicate_count",
        "notes" if "notes" in cols else "NULL AS notes",
        "order_date" if "order_date" in cols else "NULL AS order_date",
    ]
    rows = conn.execute(f"SELECT {', '.join(fields)} FROM cards ORDER BY series, sticker_number").fetchall()
    conn.close()
    cards = []
    for row in rows:
        try:
            dupes = max(0, int(row["duplicate_count"] or 0))
        except Exception:
            dupes = 0
        cards.append({
            "id": int(row["id"]),
            "series": int(row["series"]),
            "sticker_number": int(row["sticker_number"]),
            "name": display_name(row["series"], row["sticker_number"], row["sticker_name"]),
            "sticker_name": row["sticker_name"],
            "owned": normalize_owned(row["owned"]),
            "back_color": row["back_color"],
            "image": get_image_value(row, cols),
            "duplicate_count": dupes,
            "notes": row["notes"] or "",
            "order_date": row["order_date"] or "",
            "code": f"S{int(row['series']):02d}-#{int(row['sticker_number'])}",
        })
    return cards

def apply_card_filters(cards, args):
    search = (args.get("search") or "").strip().lower()
    series_filter = (args.get("series") or "").strip()
    ownership_filter = (args.get("ownership") or "").strip().lower()
    back_color_filter = (args.get("back_color") or "").strip().lower()
    sort_by = (args.get("sort") or "series_number").strip().lower()
    missing_only = (args.get("missing_only") or "").strip().lower() in {"1","true","on","yes"}
    duplicates_only = (args.get("duplicates_only") or "").strip().lower() in {"1","true","on","yes"}
    filtered = []
    for c in cards:
        if series_filter:
            try:
                if c["series"] != int(series_filter):
                    continue
            except ValueError:
                pass
        if ownership_filter == "owned" and c["owned"] != 1:
            continue
        if ownership_filter == "missing" and c["owned"] == 1:
            continue
        if missing_only and c["owned"] == 1:
            continue
        if duplicates_only and c["duplicate_count"] <= 0:
            continue
        if back_color_filter and (c["back_color"] or "").strip().lower() != back_color_filter:
            continue
        if search:
            blob = " ".join([c["name"], c["sticker_name"] or "", str(c["series"]), str(c["sticker_number"]), c["code"], c["back_color"] or "", str(c["duplicate_count"]), c["notes"] or ""]).lower()
            if search not in blob:
                continue
        filtered.append(c)
    if sort_by == "name":
        filtered.sort(key=lambda x: x["name"].lower())
    elif sort_by == "duplicates":
        filtered.sort(key=lambda x: (-x["duplicate_count"], x["series"], x["sticker_number"]))
    else:
        filtered.sort(key=lambda x: (x["series"], x["sticker_number"]))
    return filtered

def card_stats(cards):
    total_cards = len(cards)
    owned_total = sum(1 for c in cards if c["owned"] == 1)
    duplicate_total = sum(c["duplicate_count"] for c in cards)
    completion_pct = round((owned_total / total_cards) * 100, 1) if total_cards else 0
    series_progress = []
    for s in range(1, 17):
        subset = [c for c in cards if c["series"] == s]
        total = len(subset)
        owned = sum(1 for c in subset if c["owned"] == 1)
        percent = round((owned / total) * 100, 1) if total else 0
        series_progress.append({"series": s, "total": total, "owned": owned, "percent": percent})
    return total_cards, owned_total, duplicate_total, completion_pct, series_progress

def load_puzzles():
    ensure_puzzle_table()
    conn = get_db()
    rows = conn.execute("SELECT series, piece_number, owned, duplicate_count, notes FROM series_puzzle_pieces ORDER BY series, piece_number").fetchall()
    conn.close()
    grouped = {}
    for s in range(1, 17):
        grouped[s] = {"series": s, "pieces": [], "owned_count": 0, "total": PUZZLE_PIECES_PER_SERIES, "duplicate_total": 0}
    for row in rows:
        try:
            dupes = max(0, int(row["duplicate_count"] or 0))
        except Exception:
            dupes = 0
        owned = normalize_owned(row["owned"])
        piece = {"series": int(row["series"]), "piece_number": int(row["piece_number"]), "owned": owned, "duplicate_count": dupes, "notes": row["notes"] or ""}
        grouped[piece["series"]]["pieces"].append(piece)
        if owned == 1:
            grouped[piece["series"]]["owned_count"] += 1
        grouped[piece["series"]]["duplicate_total"] += dupes
    return [grouped[s] for s in range(1, 17)]

@app.route("/")
def index():
    cards = load_cards()
    filtered = apply_card_filters(cards, request.args)
    total_cards, owned_total, duplicate_total, completion_pct, series_progress = card_stats(cards)
    view_mode = (request.args.get("view") or "gallery").strip().lower()
    if view_mode not in ("gallery", "spreadsheet"):
        view_mode = "gallery"
    return render_template("index.html", cards=filtered, total_cards=total_cards, owned_total=owned_total, duplicate_total=duplicate_total, completion_pct=completion_pct, series_progress=series_progress, search=request.args.get("search", ""), series_filter=request.args.get("series", ""), ownership_filter=request.args.get("ownership", ""), back_color_filter=request.args.get("back_color", ""), sort_by=request.args.get("sort", "series_number"), view_mode=view_mode, missing_only=(request.args.get("missing_only") or "").strip().lower() in {"1","true","on","yes"}, duplicates_only=(request.args.get("duplicates_only") or "").strip().lower() in {"1","true","on","yes"}, back_color_options=BACK_COLOR_OPTIONS)

@app.route("/puzzles")
def puzzles():
    grouped = load_puzzles()
    total_pieces = sum(s["total"] for s in grouped)
    owned_pieces = sum(s["owned_count"] for s in grouped)
    duplicate_total = sum(s["duplicate_total"] for s in grouped)
    percent = round((owned_pieces / total_pieces) * 100, 1) if total_pieces else 0
    return render_template("puzzles.html", puzzle_series=grouped, total_pieces=total_pieces, owned_pieces=owned_pieces, duplicate_total=duplicate_total, percent=percent)

@app.route("/update_puzzle_piece/<int:series>/<int:piece_number>", methods=["POST"])
def update_puzzle_piece(series, piece_number):
    owned = 1 if request.form.get("owned") == "1" else 0
    notes = (request.form.get("notes") or "").strip()
    raw_dup = (request.form.get("duplicate_count") or "0").strip()
    try:
        duplicate_count = max(0, int(raw_dup))
    except ValueError:
        duplicate_count = 0
    ensure_puzzle_table()
    conn = get_db()
    conn.execute("UPDATE series_puzzle_pieces SET owned = ?, duplicate_count = ?, notes = ? WHERE series = ? AND piece_number = ?", (owned, duplicate_count, notes, series, piece_number))
    conn.commit()
    conn.close()
    flash(f"Series {series} puzzle piece {piece_number} updated.")
    return redirect(request.form.get("next") or request.referrer or url_for("puzzles"))

@app.route("/card/<int:card_id>")
def card_detail(card_id):
    cards = load_cards()
    card = next((c for c in cards if c["id"] == card_id), None)
    if not card:
        return "Card not found", 404
    return render_template("card_detail.html", card=card)

@app.route("/update_notes/<int:card_id>", methods=["POST"])
def update_notes(card_id):
    notes = (request.form.get("notes") or "").strip()
    conn = get_db()
    conn.execute("UPDATE cards SET notes = ? WHERE id = ?", (notes, card_id))
    conn.commit()
    conn.close()
    flash("Notes updated.")
    return redirect(request.form.get("next") or request.referrer or url_for("card_detail", card_id=card_id))

@app.route("/mark_owned/<int:card_id>", methods=["POST"])
def mark_owned(card_id):
    conn = get_db()
    conn.execute("UPDATE cards SET owned = 1 WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()
    flash("Card marked as owned.")
    return redirect(request.form.get("next") or request.referrer or url_for("index"))

@app.route("/mark_missing/<int:card_id>", methods=["POST"])
def mark_missing(card_id):
    conn = get_db()
    conn.execute("UPDATE cards SET owned = 0, duplicate_count = 0 WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()
    flash("Card marked as missing.")
    return redirect(request.form.get("next") or request.referrer or url_for("index"))

@app.route("/update_duplicates/<int:card_id>", methods=["POST"])
def update_duplicates(card_id):
    raw = (request.form.get("duplicate_count") or "0").strip()
    try:
        value = max(0, int(raw))
    except ValueError:
        value = 0
    conn = get_db()
    conn.execute("UPDATE cards SET duplicate_count = ? WHERE id = ?", (value, card_id))
    conn.commit()
    conn.close()
    flash("Duplicate count updated.")
    return redirect(request.form.get("next") or request.referrer or url_for("index"))

@app.route("/export/csv")
def export_csv():
    cards = load_cards()
    filtered = apply_card_filters(cards, request.args)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Series", "Number", "Name", "Status", "Duplicates", "Back Color", "Code", "Notes", "Date Ordered"])
    for c in filtered:
        writer.writerow([
            c["series"],
            c["sticker_number"],
            c["name"],
            "Owned" if c["owned"] == 1 else "Missing",
            c["duplicate_count"],
            c["back_color"] or "",
            c["code"],
            c["notes"] or "",
            c["order_date"] or "",
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=wacky-packages.csv"},
    )

@app.route("/export/txt")
def export_txt():
    cards = load_cards()
    filtered = apply_card_filters(cards, request.args)
    lines = [f"Wacky Packages - s{c['series']} #{c['sticker_number']} {c['name']}" for c in filtered]
    return Response(
        "\n".join(lines) + "\n",
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=wacky-packages.txt"},
    )

@app.route("/export/duplicates")
def export_duplicates():
    cards = load_cards()
    filtered = [c for c in cards if c["duplicate_count"] > 0]
    filtered.sort(key=lambda c: (c["series"], c["sticker_number"]))
    name_width = max((len(c["name"]) for c in filtered), default=0)
    back_width = max((len(c["back_color"] or "") for c in filtered), default=0)
    lines = []
    current_series = None
    for c in filtered:
        if c["series"] != current_series:
            if current_series is not None:
                lines.append("")
            current_series = c["series"]
            lines.append(f"Series {c['series']}")
            lines.append("")
        back = c["back_color"] or ""
        lines.append(f"{c['name'].ljust(name_width)}   {back.ljust(back_width)}   {c['duplicate_count']}")
    return Response(
        "\n".join(lines) + ("\n" if lines else ""),
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=wacky-packages-duplicates.txt"},
    )

@app.route("/export/owned")
def export_owned():
    cards = load_cards()
    series_total = {}
    series_owned = {}
    for c in cards:
        series_total[c["series"]] = series_total.get(c["series"], 0) + 1
        if c["owned"] == 1:
            series_owned[c["series"]] = series_owned.get(c["series"], 0) + 1
    cards = [c for c in cards if c["owned"] == 1]
    cards.sort(key=lambda c: (c["series"], c["sticker_number"]))
    name_width = max((len(c["name"]) for c in cards), default=0)
    num_width = max((len(str(c["sticker_number"])) for c in cards), default=0)
    lines = []
    current_series = None
    for c in cards:
        if c["series"] != current_series:
            if current_series is not None:
                lines.append("")
            current_series = c["series"]
            owned_n = series_owned.get(c["series"], 0)
            total_n = series_total.get(c["series"], 0)
            progress = f"{owned_n}/{total_n}"
            if total_n and owned_n == total_n:
                progress += "     complete series"
            lines.append(f"Series {c['series']}     {progress}")
            lines.append("")
            lines.append("")
        back = c["back_color"] or ""
        num = f"#{c['sticker_number']}".ljust(num_width + 1)
        lines.append(f"{num}  {c['name'].ljust(name_width)}   {back}")
    return Response(
        "\n".join(lines) + ("\n" if lines else ""),
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=wacky-packages-owned.txt"},
    )

@app.route("/export/missing")
def export_missing():
    cards = load_cards()
    cards = [c for c in cards if c["owned"] != 1]
    cards.sort(key=lambda c: (c["series"], c["sticker_number"]))
    lines = []
    current_series = None
    for c in cards:
        if c["series"] != current_series:
            if current_series is not None:
                lines.append("")
            current_series = c["series"]
            lines.append(f"Series {c['series']}")
            lines.append("")
        lines.append(f"#{c['sticker_number']} - {c['name']}")
    return Response(
        "\n".join(lines) + ("\n" if lines else ""),
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=wacky-packages-missing.txt"},
    )

@app.route("/export/missing_puzzle_pieces")
def export_missing_puzzle_pieces():
    grouped = load_puzzles()
    lines = []
    for series in grouped:
        missing = [p for p in series["pieces"] if p["owned"] != 1]
        if lines:
            lines.append("")
        if not missing:
            lines.append(f"Series {series['series']} - complete")
            continue
        lines.append(f"Series {series['series']}")
        lines.append("")
        for piece in missing:
            row, column = puzzle_piece_location(piece["piece_number"])
            lines.append(f"Row {row} - {column}")
    return Response(
        "\n".join(lines) + ("\n" if lines else ""),
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=wacky-packages-missing-puzzle-pieces.txt"},
    )

@app.route("/export/orders")
def export_orders():
    date_from = (request.args.get("from") or "").strip()
    date_to = (request.args.get("to") or "").strip()
    cards = load_cards()
    cards = [c for c in cards if c["order_date"]]
    if date_from:
        cards = [c for c in cards if c["order_date"] >= date_from]
    if date_to:
        cards = [c for c in cards if c["order_date"] <= date_to]
    cards.sort(key=lambda c: (c["series"], c["name"], c["order_date"]))
    name_width = max((len(c["name"]) for c in cards), default=0)
    lines = []
    current_series = None
    for c in cards:
        if c["series"] != current_series:
            if current_series is not None:
                lines.append("")
            current_series = c["series"]
            lines.append(f"Series {c['series']}")
            lines.append("")
        lines.append(f"{c['name'].ljust(name_width)}   {c['order_date']}")
    return Response(
        "\n".join(lines) + ("\n" if lines else ""),
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=wacky-packages-orders.txt"},
    )

@app.route("/update_back_color/<int:card_id>", methods=["POST"])
def update_back_color(card_id):
    value = request.form.get("back_color") or None
    conn = get_db()
    conn.execute("UPDATE cards SET back_color = ? WHERE id = ?", (value, card_id))
    conn.commit()
    conn.close()
    flash("Back color updated.")
    return redirect(request.form.get("next") or request.referrer or url_for("index"))

@app.route("/update_order_date/<int:card_id>", methods=["POST"])
def update_order_date(card_id):
    value = request.form.get("order_date") or None
    conn = get_db()
    conn.execute("UPDATE cards SET order_date = ? WHERE id = ?", (value, card_id))
    conn.commit()
    conn.close()
    flash("Order date updated.")
    return redirect(request.form.get("next") or request.referrer or url_for("index"))


# ---------------------------------------------------------------------------
# eBay Research
# ---------------------------------------------------------------------------

def research_rule_form(form):
    def as_float(name):
        raw = (form.get(name) or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    raw_card = (form.get("linked_card_id") or "").strip()
    linked_card_id = int(raw_card) if raw_card.isdigit() else None

    # Browser datalist behavior can vary. If JS did not populate the hidden
    # card ID, resolve the visible label on the server. Expected format:
    #   Series 3 #7 · Grime Dog Food
    # Optional back text after the sticker name is harmless.
    if linked_card_id is None:
        label = (form.get("linked_card_label") or "").strip()
        match = re.match(r"^Series\s+(\d+)\s+#(\d+)\s+·\s+(.+)$", label, re.I)
        if match:
            series = int(match.group(1))
            sticker_number = int(match.group(2))
            conn = get_db()
            row = conn.execute(
                """
                SELECT id
                FROM cards
                WHERE series=? AND sticker_number=?
                ORDER BY id
                LIMIT 1
                """,
                (series, sticker_number),
            ).fetchone()
            conn.close()
            if row:
                linked_card_id = int(row["id"])

    return {
        "name": (form.get("name") or "").strip(),
        "query": (form.get("query") or "").strip(),
        "linked_card_id": linked_card_id,
        "linked_card_label": (form.get("linked_card_label") or "").strip(),
        "enabled": 1 if form.get("enabled") == "on" else 0,
        "min_price": as_float("min_price"),
        "max_price": as_float("max_price"),
        "target_buy_price": as_float("target_buy_price"),
        "min_seller_feedback": as_float("min_seller_feedback") or 97,
        "match_mode": (form.get("match_mode") or "balanced").strip().lower(),
        "product_filter": (form.get("product_filter") or "any").strip().lower(),
        "grader_filter": (form.get("grader_filter") or "").strip().upper() or None,
        "grade_filter": as_float("grade_filter"),
        "target_scope": (form.get("target_scope") or "card").strip().lower(),
        "target_series": (
            int(form.get("target_series"))
            if (form.get("target_series") or "").isdigit()
            else None
        ),
    }

@app.route("/research")
def research():
    ensure_research_schema()
    conn = get_db()
    clauses = ["is_hidden=0", "listing_status='active'"]
    params = []

    verdict = (request.args.get("verdict") or "").strip().upper()
    search = (request.args.get("search") or "").strip()
    watched = request.args.get("watched") == "1"
    target_hits = request.args.get("target_hits") == "1"
    price_drops = request.args.get("price_drops") == "1"

    verdicts = [v for v in verdict.split(",") if v]
    if verdicts:
        clauses.append(f"verdict IN ({','.join('?' * len(verdicts))})")
        params.extend(verdicts)
    if search:
        clauses.append("(title LIKE ? OR sticker_name LIKE ? OR seller_username LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term])
    if watched:
        clauses.append("is_watched=1")
    if target_hits:
        clauses.append("target_price_hit=1")
    if price_drops:
        clauses.append("price_drop_amount>0")

    rows = conn.execute(
        f"""
        SELECT l.*, r.name AS rule_name
        FROM ebay_listings l
        LEFT JOIN ebay_search_rules r ON r.id=l.search_rule_id
        WHERE {' AND '.join(clauses)}
        ORDER BY target_price_hit DESC,
          CASE verdict WHEN 'BUY' THEN 1 WHEN 'GOOD' THEN 2 WHEN 'FAIR' THEN 3
                       WHEN 'RISK' THEN 4 WHEN 'PASS' THEN 5 ELSE 6 END,
          deal_score DESC, discount_pct DESC, last_seen DESC
        LIMIT 500
        """,
        params,
    ).fetchall()

    stats = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN verdict='BUY' THEN 1 ELSE 0 END) AS buys,
          SUM(CASE WHEN verdict='GOOD' THEN 1 ELSE 0 END) AS good,
          SUM(CASE WHEN verdict='FAIR' THEN 1 ELSE 0 END) AS fair,
          SUM(CASE WHEN verdict='UNPRICED' THEN 1 ELSE 0 END) AS unpriced,
          SUM(CASE WHEN target_price_hit=1 THEN 1 ELSE 0 END) AS target_hits,
          SUM(CASE WHEN is_watched=1 THEN 1 ELSE 0 END) AS watched,
          SUM(CASE WHEN price_drop_amount>0 THEN 1 ELSE 0 END) AS price_drops
        FROM ebay_listings
        WHERE is_hidden=0 AND listing_status='active'
        """
    ).fetchone()

    last_scan = conn.execute(
        "SELECT * FROM ebay_scan_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return render_template(
        "research.html", rows=rows, stats=stats, last_scan=last_scan,
        search=search, verdict=verdict, watched=watched, target_hits=target_hits,
        price_drops=price_drops,
    )

@app.post("/research/scan")
def research_scan():
    try:
        result = run_research_scan(get_db, trigger_type="manual")
        if result.get("busy"):
            flash("An eBay research scan is already running.")
        else:
            flash(
                f"eBay scan complete: {result['searches']} searches, "
                f"{result['accepted_hits']} accepted of {result['raw_hits']} raw hits, "
                f"{result['new']} new, {result['price_drops']} price drops. "
                f"Rejected: {result['rejected_unrelated']} unrelated, "
                f"{result['rejected_conflict']} identity conflicts, "
                f"{result['rejected_multichoice']} multi-choice, "
                f"{result['rejected_modern']} modern/reprint, "
                f"{result['rejected_product_filter']} product-filter, "
                f"{result['rejected_era_format']} era/format."
            )
    except Exception as exc:
        flash(f"eBay scan failed: {exc}")
    return redirect(url_for("research"))

@app.route("/research/rules")
def research_rules():
    ensure_research_schema()
    conn = get_db()
    rules = conn.execute(
        """
        SELECT r.*, c.series, c.sticker_number, c.sticker_name
        FROM ebay_search_rules r
        LEFT JOIN cards c ON c.id=r.linked_card_id
        ORDER BY r.enabled DESC, r.name COLLATE NOCASE
        """
    ).fetchall()
    conn.close()
    return render_template("research_rules.html", rules=rules)

@app.route("/research/rules/new", methods=["GET","POST"])
def research_rule_new():
    ensure_research_schema()
    cards = load_cards()
    if request.method == "POST":
        data = research_rule_form(request.form)
        if not data["name"] or not data["query"]:
            flash("Rule name and eBay query are required.")
            return render_template("research_rule_form.html", rule=data, cards=cards, mode="new")
        conn = get_db()
        now = utcnow()
        conn.execute(
            """
            INSERT INTO ebay_search_rules(
              name,query,linked_card_id,enabled,min_price,max_price,
              target_buy_price,min_seller_feedback,match_mode,product_filter,
                grader_filter,grade_filter,target_scope,target_series,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                data["name"], data["query"], data["linked_card_id"], data["enabled"],
                data["min_price"], data["max_price"], data["target_buy_price"],
                data["min_seller_feedback"], data["match_mode"], data["product_filter"],
                data["grader_filter"], data["grade_filter"], data["target_scope"],
                data["target_series"], now, now,
            ),
        )
        conn.commit()
        conn.close()
        flash("eBay research rule created.")
        return redirect(url_for("research_rules"))
    return render_template("research_rule_form.html", rule=None, cards=cards, mode="new")

@app.route("/research/rules/<int:rule_id>/edit", methods=["GET","POST"])
def research_rule_edit(rule_id):
    ensure_research_schema()
    cards = load_cards()
    conn = get_db()
    rule = conn.execute("SELECT * FROM ebay_search_rules WHERE id=?", (rule_id,)).fetchone()
    if not rule:
        conn.close()
        return "Rule not found", 404
    if request.method == "POST":
        data = research_rule_form(request.form)
        conn.execute(
            """
            UPDATE ebay_search_rules SET
              name=?,query=?,linked_card_id=?,enabled=?,min_price=?,max_price=?,
              target_buy_price=?,min_seller_feedback=?,match_mode=?,product_filter=?,
                grader_filter=?,grade_filter=?,target_scope=?,target_series=?,updated_at=?
            WHERE id=?
            """,
            (
                data["name"], data["query"], data["linked_card_id"], data["enabled"],
                data["min_price"], data["max_price"], data["target_buy_price"],
                data["min_seller_feedback"], data["match_mode"], data["product_filter"],
                data["grader_filter"], data["grade_filter"], data["target_scope"],
                data["target_series"], utcnow(), rule_id,
            ),
        )
        conn.commit()
        conn.close()
        flash("eBay research rule updated.")
        return redirect(url_for("research_rules"))
    conn.close()
    return render_template("research_rule_form.html", rule=rule, cards=cards, mode="edit")

@app.post("/research/rules/<int:rule_id>/toggle")
def research_rule_toggle(rule_id):
    conn = get_db()
    row = conn.execute("SELECT enabled FROM ebay_search_rules WHERE id=?", (rule_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE ebay_search_rules SET enabled=?,updated_at=? WHERE id=?",
            (0 if row["enabled"] else 1, utcnow(), rule_id),
        )
        conn.commit()
    conn.close()
    return redirect(url_for("research_rules"))

@app.post("/research/rules/<int:rule_id>/delete")
def research_rule_delete(rule_id):
    conn = get_db()
    conn.execute("DELETE FROM ebay_search_rules WHERE id=?", (rule_id,))
    conn.commit()
    conn.close()
    flash("eBay research rule deleted.")
    return redirect(url_for("research_rules"))

@app.post("/research/listing/<int:listing_id>/watch")
def research_watch(listing_id):
    conn = get_db()
    row = conn.execute("SELECT is_watched FROM ebay_listings WHERE id=?", (listing_id,)).fetchone()
    if row:
        conn.execute(
            "UPDATE ebay_listings SET is_watched=? WHERE id=?",
            (0 if row["is_watched"] else 1, listing_id),
        )
        conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("research"))

@app.post("/research/listing/<int:listing_id>/hide")
def research_hide(listing_id):
    conn = get_db()
    conn.execute("UPDATE ebay_listings SET is_hidden=1 WHERE id=?", (listing_id,))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("research"))

@app.route("/research/history/<int:listing_id>")
def research_history(listing_id):
    conn = get_db()
    listing = conn.execute("SELECT * FROM ebay_listings WHERE id=?", (listing_id,)).fetchone()
    if not listing:
        conn.close()
        return "Listing not found", 404
    history = conn.execute(
        """
        SELECT * FROM ebay_price_history
        WHERE listing_id=? OR ebay_item_id=?
        ORDER BY observed_at
        """,
        (listing_id, listing["ebay_item_id"]),
    ).fetchall()
    chart = {
        "labels": [r["observed_at"] for r in history],
        "listing": [r["total_cost"] for r in history],
        "market": [r["market_value"] for r in history],
    }
    conn.close()
    return render_template(
        "research_history.html", listing=listing, history=history,
        chart_json=json.dumps(chart),
    )


@app.route("/research/rejected")
def research_rejected():
    ensure_research_schema()
    conn = get_db()

    reason = (request.args.get("reason") or "").strip()
    run_id = (request.args.get("run_id") or "").strip()
    search = (request.args.get("search") or "").strip()

    clauses = ["1=1"]
    params = []

    if reason:
        clauses.append("h.rejection_reason=?")
        params.append(reason)

    if run_id.isdigit():
        clauses.append("h.scan_run_id=?")
        params.append(int(run_id))

    if search:
        term = f"%{search}%"
        clauses.append(
            "(h.title LIKE ? OR c.sticker_name LIKE ? OR r.name LIKE ?)"
        )
        params.extend([term, term, term])

    rows = conn.execute(
        f"""
        SELECT
          h.*,
          r.name AS rule_name,
          c.series AS linked_series,
          c.sticker_number AS linked_sticker_number,
          c.sticker_name AS linked_sticker_name
        FROM ebay_rejected_hits h
        LEFT JOIN ebay_search_rules r ON r.id=h.search_rule_id
        LEFT JOIN cards c ON c.id=h.linked_card_id
        WHERE {' AND '.join(clauses)}
        ORDER BY h.id DESC
        LIMIT 1000
        """,
        params,
    ).fetchall()

    stats = conn.execute(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN rejection_reason='unrelated' THEN 1 ELSE 0 END) AS unrelated,
          SUM(CASE WHEN rejection_reason='conflict' THEN 1 ELSE 0 END) AS conflict,
          SUM(CASE WHEN rejection_reason='multichoice' THEN 1 ELSE 0 END) AS multichoice,
          SUM(CASE WHEN rejection_reason='modern' THEN 1 ELSE 0 END) AS modern,
          SUM(CASE WHEN rejection_reason='product_filter' THEN 1 ELSE 0 END) AS product_filter,
          SUM(CASE WHEN rejection_reason='era_format' THEN 1 ELSE 0 END) AS era_format
        FROM ebay_rejected_hits
        """
    ).fetchone()

    runs = conn.execute(
        """
        SELECT id, started_at, trigger_type
        FROM ebay_scan_runs
        ORDER BY id DESC
        LIMIT 50
        """
    ).fetchall()

    conn.close()
    return render_template(
        "research_rejected.html",
        rows=rows,
        stats=stats,
        runs=runs,
        reason=reason,
        run_id=run_id,
        search=search,
    )

@app.route("/research/scans/<int:run_id>/rejected")
def research_scan_rejected(run_id):
    return redirect(url_for("research_rejected", run_id=run_id))

@app.route("/research/scans")
def research_scans():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM ebay_scan_runs ORDER BY id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return render_template("research_scans.html", rows=rows)

@app.route("/research/automation", methods=["GET","POST"])
def research_automation():
    ensure_research_schema()
    if request.method == "POST":
        enabled = "1" if request.form.get("enabled") == "on" else "0"
        try:
            interval = max(15, min(1440, int(request.form.get("interval") or 30)))
        except ValueError:
            interval = 30
        try:
            stale = max(1, min(20, int(request.form.get("stale_after") or 3)))
        except ValueError:
            stale = 3
        conn = get_db()
        for key, value in [
            ("auto_scan_enabled", enabled),
            ("auto_scan_interval_minutes", str(interval)),
            ("stale_after_misses", str(stale)),
        ]:
            conn.execute(
                """
                INSERT INTO ebay_app_settings(key,value) VALUES (?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, value),
            )
        conn.commit()
        conn.close()
        reschedule(app, get_db)
        flash("Research automation settings saved.")
        return redirect(url_for("research_automation"))

    conn = get_db()
    settings = {
        row["key"]: row["value"]
        for row in conn.execute("SELECT key,value FROM ebay_app_settings")
    }
    conn.close()
    return render_template(
        "research_automation.html", settings=settings,
        scheduler=scheduler_status(),
    )

@app.route("/research/inactive")
def research_inactive():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM ebay_listings
        WHERE listing_status IN ('stale','ended','invalid_match')
        ORDER BY last_seen DESC
        LIMIT 500
        """
    ).fetchall()
    conn.close()
    return render_template("research_inactive.html", rows=rows)


if __name__ == "__main__":
    USE_RELOADER = True
    # The reloader re-execs this whole script in a child process; only run
    # one-time startup (including the scheduler) in the process that's
    # actually serving, not the reloader's watcher process.
    if not USE_RELOADER or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        ensure_card_columns()
        ensure_puzzle_table()
        ensure_research_schema()
        start_scheduler(app, get_db)
    app.run(host="0.0.0.0", port=5050, debug=True, use_reloader=USE_RELOADER)
