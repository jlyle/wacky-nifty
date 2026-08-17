
from datetime import datetime, timezone

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def ensure_research_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ebay_search_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        query TEXT NOT NULL,
        linked_card_id INTEGER,
        enabled INTEGER NOT NULL DEFAULT 1,
        min_price REAL,
        max_price REAL,
        target_buy_price REAL,
        min_seller_feedback REAL DEFAULT 97,
        match_mode TEXT NOT NULL DEFAULT 'balanced',
        product_filter TEXT NOT NULL DEFAULT 'any',
        grader_filter TEXT,
        grade_filter REAL,
        target_scope TEXT NOT NULL DEFAULT 'card',
        target_series INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS ebay_listings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ebay_item_id TEXT NOT NULL UNIQUE,
        search_rule_id INTEGER,
        linked_card_id INTEGER,
        title TEXT NOT NULL,
        series INTEGER,
        sticker_name TEXT,
        sticker_number INTEGER,
        back_variant TEXT,
        product_type TEXT,
        grader TEXT,
        grade REAL,
        raw_condition TEXT,
        quantity INTEGER DEFAULT 1,
        condition_flags TEXT,
        comparison_key TEXT,
        comparable_count INTEGER DEFAULT 0,
        comp_raw_clean INTEGER DEFAULT 0,
        comp_after_dedupe INTEGER DEFAULT 0,
        comp_unique_sellers INTEGER DEFAULT 0,
        price REAL,
        shipping REAL,
        total_cost REAL,
        market_value REAL,
        discount_pct REAL,
        deal_score INTEGER DEFAULT 0,
        verdict TEXT DEFAULT 'UNPRICED',
        seller_username TEXT,
        seller_feedback REAL,
        seller_feedback_count INTEGER,
        item_url TEXT,
        image_url TEXT,
        item_end_date TEXT,
        is_watched INTEGER DEFAULT 0,
        is_hidden INTEGER DEFAULT 0,
        target_buy_price REAL,
        target_price_hit INTEGER DEFAULT 0,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        listing_status TEXT DEFAULT 'active',
        miss_count INTEGER DEFAULT 0,
        ended_at TEXT,
        last_total_cost REAL,
        price_drop_amount REAL DEFAULT 0,
        price_drop_pct REAL DEFAULT 0,
        last_price_change_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_ebay_listings_rule
      ON ebay_listings(search_rule_id);
    CREATE INDEX IF NOT EXISTS idx_ebay_listings_card
      ON ebay_listings(linked_card_id);
    CREATE INDEX IF NOT EXISTS idx_ebay_listings_key
      ON ebay_listings(comparison_key);

    CREATE TABLE IF NOT EXISTS ebay_price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ebay_item_id TEXT NOT NULL,
        listing_id INTEGER,
        observed_at TEXT NOT NULL,
        total_cost REAL,
        market_value REAL,
        deal_score INTEGER,
        verdict TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_wacky_price_history_item
      ON ebay_price_history(ebay_item_id, observed_at);


    CREATE TABLE IF NOT EXISTS ebay_rejected_hits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_run_id INTEGER NOT NULL,
        search_rule_id INTEGER,
        linked_card_id INTEGER,
        ebay_item_id TEXT,
        title TEXT NOT NULL,
        item_url TEXT,
        rejection_reason TEXT NOT NULL,
        parsed_series INTEGER,
        parsed_sticker_number INTEGER,
        parsed_sticker_name TEXT,
        parsed_back_variant TEXT,
        parsed_product_type TEXT,
        parsed_grader TEXT,
        parsed_grade REAL,
        parsed_raw_condition TEXT,
        parsed_quantity INTEGER,
        condition_flags TEXT,
        name_similarity REAL,
        match_reason TEXT,
        is_modern_issue INTEGER DEFAULT 0,
        explicit_years TEXT,
        modern_labels TEXT,
        product_filter_detail TEXT,
        is_era_format_issue INTEGER DEFAULT 0,
        era_format_labels TEXT,
        off_era_years TEXT,
        era_format_detail TEXT,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_rejected_hits_scan
      ON ebay_rejected_hits(scan_run_id);
    CREATE INDEX IF NOT EXISTS idx_rejected_hits_reason
      ON ebay_rejected_hits(rejection_reason);

    CREATE TABLE IF NOT EXISTS ebay_scan_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        trigger_type TEXT DEFAULT 'manual',
        status TEXT NOT NULL,
        searches_run INTEGER DEFAULT 0,
        listings_seen INTEGER DEFAULT 0,
        new_listings INTEGER DEFAULT 0,
        price_drops INTEGER DEFAULT 0,
        stale_marked INTEGER DEFAULT 0,
        duration_seconds REAL,
        raw_hits INTEGER DEFAULT 0,
        accepted_hits INTEGER DEFAULT 0,
        rejected_unrelated INTEGER DEFAULT 0,
        rejected_conflict INTEGER DEFAULT 0,
        rejected_multichoice INTEGER DEFAULT 0,
        rejected_modern INTEGER DEFAULT 0,
        rejected_product_filter INTEGER DEFAULT 0,
        rejected_era_format INTEGER DEFAULT 0,
        error TEXT
    );

    CREATE TABLE IF NOT EXISTS ebay_app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    INSERT OR IGNORE INTO ebay_app_settings(key,value) VALUES
      ('auto_scan_enabled','0'),
      ('auto_scan_interval_minutes','30'),
      ('stale_after_misses','3');
    """)
    conn.commit()
    ensure_research_migrations(conn)


def ensure_column(conn, table_name, column_name, definition):
    cols = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in cols:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )

def ensure_research_migrations(conn):
    ensure_column(conn, "ebay_search_rules", "match_mode", "TEXT NOT NULL DEFAULT 'balanced'")
    ensure_column(conn, "ebay_search_rules", "product_filter", "TEXT NOT NULL DEFAULT 'any'")
    ensure_column(conn, "ebay_search_rules", "grader_filter", "TEXT")
    ensure_column(conn, "ebay_search_rules", "grade_filter", "REAL")
    ensure_column(conn, "ebay_search_rules", "target_scope", "TEXT NOT NULL DEFAULT 'card'")
    ensure_column(conn, "ebay_search_rules", "target_series", "INTEGER")
    ensure_column(conn, "ebay_listings", "comp_raw_clean", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_listings", "comp_after_dedupe", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_listings", "comp_unique_sellers", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_listings", "raw_condition", "TEXT")
    ensure_column(conn, "ebay_rejected_hits", "parsed_raw_condition", "TEXT")
    ensure_column(conn, "ebay_scan_runs", "raw_hits", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_scan_runs", "accepted_hits", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_scan_runs", "rejected_unrelated", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_scan_runs", "rejected_conflict", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_scan_runs", "rejected_multichoice", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_scan_runs", "rejected_modern", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_scan_runs", "rejected_product_filter", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_scan_runs", "rejected_era_format", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_rejected_hits", "is_modern_issue", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_rejected_hits", "explicit_years", "TEXT")
    ensure_column(conn, "ebay_rejected_hits", "modern_labels", "TEXT")
    ensure_column(conn, "ebay_rejected_hits", "product_filter_detail", "TEXT")
    ensure_column(conn, "ebay_rejected_hits", "is_era_format_issue", "INTEGER DEFAULT 0")
    ensure_column(conn, "ebay_rejected_hits", "era_format_labels", "TEXT")
    ensure_column(conn, "ebay_rejected_hits", "off_era_years", "TEXT")
    ensure_column(conn, "ebay_rejected_hits", "era_format_detail", "TEXT")
    conn.commit()
