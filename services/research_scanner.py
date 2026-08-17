
from datetime import datetime, timezone
import statistics
from collections import defaultdict
import threading
import time

from services.ebay import get_app_token, search_items
from services.research_db import ensure_research_tables, utcnow
from services.wacky_parser import parse_listing, parse_complete_series_listing
from services.deal_score import calculate_deal

_scan_lock = threading.Lock()

def _card(conn, card_id):
    if not card_id:
        return None
    return conn.execute(
        "SELECT id, series, sticker_number, sticker_name, back_color FROM cards WHERE id=?",
        (card_id,),
    ).fetchone()

def _flags_text(flags):
    return ", ".join(flags or [])



def build_ebay_query(rule, linked_card):
    """Broaden or tighten the outbound eBay query based on rule scope."""
    mode = (rule["match_mode"] or "balanced").strip().lower()
    target_scope = (rule["target_scope"] or "card").strip().lower()

    if target_scope == "series":
        series = rule["target_series"]
        if mode == "strict":
            return rule["query"]
        if mode == "broad":
            return f'Wacky Packages Series {series} complete set'
        return f'"Wacky Packages" "Series {series}" "complete set"'

    if not linked_card:
        return rule["query"]

    name = linked_card["sticker_name"]

    if mode == "strict":
        return rule["query"]

    if mode == "broad":
        return f'Wacky Packages {name}'

    return f'Wacky Packages "{name}"'

def rejection_reason(parsed):
    flags = set(parsed.get("condition_flags") or [])
    if parsed.get("product_filter_reject"):
        return "product_filter"
    if parsed.get("is_modern_issue") or "MODERN/REPRINT" in flags:
        return "modern"
    if parsed.get("is_era_format_issue") or "ERA/FORMAT" in flags:
        return "era_format"
    if "MULTI-CHOICE" in flags:
        return "multichoice"
    if parsed.get("series_conflict") or parsed.get("number_conflict"):
        return "conflict"
    return "unrelated"

def revalidate_rule_listings(conn, rule, linked_card):
    """Immediately invalidate stored rows that no longer satisfy a linked rule."""
    if not linked_card:
        return 0

    rows = conn.execute(
        """
        SELECT id, title
        FROM ebay_listings
        WHERE search_rule_id=? AND listing_status='active'
        """,
        (rule["id"],),
    ).fetchall()

    invalidated = 0
    for row in rows:
        parsed = parse_listing(row["title"], linked_card, rule["match_mode"])
        if not parsed.get("linked_match"):
            conn.execute(
                """
                UPDATE ebay_listings
                SET listing_status='invalid_match',
                    verdict='PASS',
                    deal_score=0,
                    market_value=NULL,
                    discount_pct=NULL,
                    target_price_hit=0
                WHERE id=?
                """,
                (row["id"],),
            )
            invalidated += 1

    if invalidated:
        conn.commit()

    return invalidated



def record_rejected_hit(conn, run_id, rule, linked_card, item, reason):
    flags = ", ".join(item.get("condition_flags") or [])
    conn.execute(
        """
        INSERT INTO ebay_rejected_hits (
            scan_run_id, search_rule_id, linked_card_id, ebay_item_id,
            title, item_url, rejection_reason,
            parsed_series, parsed_sticker_number, parsed_sticker_name,
            parsed_back_variant, parsed_product_type, parsed_grader,
            parsed_grade, parsed_raw_condition, parsed_quantity, condition_flags,
            name_similarity, match_reason, is_modern_issue, explicit_years,
            modern_labels, product_filter_detail, is_era_format_issue,
            era_format_labels, off_era_years, era_format_detail, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            run_id,
            rule["id"],
            linked_card["id"] if linked_card else None,
            item.get("ebay_item_id"),
            item.get("title") or "",
            item.get("item_url"),
            reason,
            item.get("series"),
            item.get("sticker_number"),
            item.get("sticker_name"),
            item.get("back_variant"),
            item.get("product_type"),
            item.get("grader"),
            item.get("grade"),
            item.get("raw_condition"),
            item.get("quantity"),
            flags,
            item.get("name_similarity"),
            item.get("match_reason"),
            1 if item.get("is_modern_issue") else 0,
            ",".join(str(y) for y in (item.get("explicit_years") or [])),
            ", ".join(item.get("modern_labels") or []),
            item.get("product_filter_reject"),
            1 if item.get("is_era_format_issue") else 0,
            ", ".join(item.get("era_format_labels") or []),
            ",".join(str(y) for y in (item.get("off_era_years") or [])),
            item.get("era_format_detail"),
            utcnow(),
        ),
    )



def normalize_comp_title(title):
    """Normalize a listing title for duplicate-family detection."""
    import re
    text = (title or "").upper()
    text = re.sub(r"\*D\d+\b", " ", text)
    text = re.sub(r"\bDUP(?:E|LICATE)?\s*\d*\b", " ", text)
    text = re.sub(r"\bUPDATED\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def seller_key(item):
    return (item.get("seller_username") or "").strip().lower() or "__unknown__"

def build_clean_comp_values(items):
    """
    Safer comparable sample:
      - clean, single-item listings only
      - collapse same-seller duplicate-title families
      - cap each seller at two listings per exact comparable group
    """
    by_key = defaultdict(list)

    for item in items:
        if item.get("condition_flags") or int(item.get("quantity") or 1) != 1:
            continue
        by_key[item["comparison_key"]].append(item)

    values_by_key = {}
    diagnostics = {}

    for key, group in by_key.items():
        seen_family = set()
        deduped = []

        for item in sorted(group, key=lambda x: float(x["total_cost"])):
            family = (
                seller_key(item),
                normalize_comp_title(item.get("title")),
            )
            if family in seen_family:
                continue
            seen_family.add(family)
            deduped.append(item)

        per_seller = defaultdict(int)
        seller_capped = []
        for item in sorted(deduped, key=lambda x: float(x["total_cost"])):
            skey = seller_key(item)
            if per_seller[skey] >= 2:
                continue
            per_seller[skey] += 1
            seller_capped.append(item)

        values = [float(item["total_cost"]) for item in seller_capped]
        values_by_key[key] = values
        diagnostics[key] = {
            "raw_clean": len(group),
            "after_dedupe": len(deduped),
            "after_seller_cap": len(seller_capped),
            "unique_sellers": len({seller_key(i) for i in seller_capped}),
        }

    return values_by_key, diagnostics


def product_filter_reason(rule, item):
    """
    Return None when the listing satisfies the rule's product constraints,
    otherwise return a short diagnostic string.
    """
    product_filter = (rule["product_filter"] or "any").strip().lower()
    grader_filter = (rule["grader_filter"] or "").strip().upper()
    grade_filter = rule["grade_filter"]

    is_graded = bool(item.get("grader"))

    if product_filter == "raw" and is_graded:
        return "graded listing rejected by raw-only rule"

    if product_filter == "graded" and not is_graded:
        return "raw listing rejected by graded-only rule"

    if product_filter == "graded" and is_graded:
        if grader_filter and (item.get("grader") or "").upper() != grader_filter:
            return f"{item.get('grader') or 'unknown grader'} rejected; rule requires {grader_filter}"

        if grade_filter is not None:
            try:
                item_grade = float(item.get("grade")) if item.get("grade") is not None else None
                required_grade = float(grade_filter)
            except (TypeError, ValueError):
                item_grade = None
                required_grade = None

            if item_grade is None or required_grade is None or abs(item_grade - required_grade) > 0.001:
                return f"grade {item.get('grade') or 'unknown'} rejected; rule requires {grade_filter:g}"

    return None


def normalize_persistence_fields(item):
    """Populate optional fields expected by the shared listing INSERT path."""
    defaults = {
        "linked_card_id": None,
        "target_buy_price": None,
        "target_price_hit": 0,
        "item_end_date": None,
        "seller_feedback_count": None,
        "product_filter_reject": None,
    }
    for key, value in defaults.items():
        item.setdefault(key, value)
    return item


def revalidate_series_rule_listings(conn, rule):
    """
    Re-check already-saved listings for a complete-Series rule using the
    current parser safeguards. This immediately retires stale rows that were
    accepted by older app versions (for example 2004 All New Series 1).
    """
    rows = conn.execute(
        """
        SELECT id, title
        FROM ebay_listings
        WHERE search_rule_id=?
          AND listing_status='active'
        """,
        (rule["id"],),
    ).fetchall()

    retired = 0
    for row in rows:
        parsed = parse_complete_series_listing(
            row["title"], rule["target_series"]
        )

        filter_reason = product_filter_reason(rule, parsed)
        valid = bool(parsed.get("linked_match")) and not filter_reason

        if not valid:
            conn.execute(
                """
                UPDATE ebay_listings
                SET listing_status='invalid_match'
                WHERE id=?
                """,
                (row["id"],),
            )
            retired += 1

    return retired

def run_research_scan(get_db, trigger_type="manual"):
    if not _scan_lock.acquire(blocking=False):
        return {"ok": False, "busy": True}

    started = utcnow()
    timer = time.monotonic()
    conn = get_db()
    ensure_research_tables(conn)

    run_id = conn.execute(
        "INSERT INTO ebay_scan_runs(started_at,trigger_type,status) VALUES (?,?,?)",
        (started, trigger_type, "running"),
    ).lastrowid
    conn.commit()

    searches_run = listings_seen = new_listings = price_drops = stale_marked = 0
    raw_hits = accepted_hits = rejected_unrelated = rejected_conflict = rejected_multichoice = rejected_modern = rejected_product_filter = rejected_era_format = 0

    try:
        token = get_app_token()
        rules = conn.execute(
            "SELECT * FROM ebay_search_rules WHERE enabled=1 ORDER BY id"
        ).fetchall()

        for rule in rules:
            searches_run += 1
            linked_card = _card(conn, rule["linked_card_id"])
            if (rule["target_scope"] or "card") == "series":
                revalidate_series_rule_listings(conn, rule)
            else:
                revalidate_rule_listings(conn, rule, linked_card)

            query = build_ebay_query(rule, linked_card)
            items = search_items(
                token,
                query,
                rule["min_price"],
                rule["max_price"],
                limit=75,
            )
            raw_hits += len(items)
            parsed_items = []
            for item in items:
                if (rule["target_scope"] or "card") == "series":
                    parsed = parse_complete_series_listing(
                        item["title"], rule["target_series"]
                    )
                else:
                    parsed = parse_listing(
                        item["title"], linked_card, rule["match_mode"]
                    )
                item.update(parsed)

                filter_reason = product_filter_reason(rule, item)
                if filter_reason:
                    item["product_filter_reject"] = filter_reason
                    item["match_reason"] = "product_filter"
                    record_rejected_hit(
                        conn, run_id, rule, linked_card, item, "product_filter"
                    )
                    rejected_product_filter += 1
                    continue

                if (
                    ((rule["target_scope"] or "card") == "series" and not item.get("linked_match"))
                    or (linked_card and not item.get("linked_match"))
                ):
                    reason = rejection_reason(item)
                    record_rejected_hit(
                        conn, run_id, rule, linked_card, item, reason
                    )
                    if reason == "modern":
                        rejected_modern += 1
                    elif reason == "era_format":
                        rejected_era_format += 1
                    elif reason == "multichoice":
                        rejected_multichoice += 1
                    elif reason == "conflict":
                        rejected_conflict += 1
                    else:
                        rejected_unrelated += 1
                    continue

                normalize_persistence_fields(item)

                # Normalize fields consumed by the common persistence path.
                # Complete-Series rules have no linked collection card, so
                # linked_card_id must be explicit rather than assumed.
                item["search_rule_id"] = rule["id"]
                item["linked_card_id"] = linked_card["id"] if linked_card else None
                item["target_buy_price"] = rule["target_buy_price"]
                item["target_price_hit"] = (
                    1 if rule["target_buy_price"] is not None
                    and item["total_cost"] <= rule["target_buy_price"] else 0
                )
                parsed_items.append(item)

            listings_seen += len(parsed_items)
            accepted_hits += len(parsed_items)

            # Market value: exact comparable groups with duplicate-family
            # collapse and seller-concentration control.
            groups, comp_diag = build_clean_comp_values(parsed_items)

            medians = {}
            for key, values in groups.items():
                diag = comp_diag.get(key, {})
                # Require at least 3 clean comps and 2 unique sellers.
                if len(values) >= 3 and int(diag.get("unique_sellers", 0)) >= 2:
                    medians[key] = round(float(statistics.median(values)), 2)

            for item in parsed_items:
                previous = conn.execute(
                    "SELECT * FROM ebay_listings WHERE ebay_item_id=?",
                    (item["ebay_item_id"],),
                ).fetchone()
                is_new = previous is None
                if is_new:
                    new_listings += 1

                previous_total = previous["total_cost"] if previous else None
                drop_amount = drop_pct = 0.0
                last_change = None
                if previous_total is not None and item["total_cost"] < previous_total:
                    drop_amount = round(previous_total - item["total_cost"], 2)
                    drop_pct = round((drop_amount / previous_total) * 100, 2) if previous_total else 0
                    last_change = utcnow()
                    price_drops += 1

                market = medians.get(item["comparison_key"])
                comparable_count = len(groups.get(item["comparison_key"], []))
                discount, score, verdict = calculate_deal(
                    item["total_cost"],
                    market,
                    seller_feedback=item["seller_feedback"],
                    comparable_count=comparable_count,
                    confidence_score=item["confidence"],
                    condition_flags=item["condition_flags"],
                    quantity=item["quantity"],
                )

                now = utcnow()
                conn.execute(
                    """
                    INSERT INTO ebay_listings (
                        ebay_item_id, search_rule_id, linked_card_id, title,
                        series, sticker_name, sticker_number, back_variant,
                        product_type, grader, grade, raw_condition, quantity, condition_flags,
                        comparison_key, comparable_count, comp_raw_clean,
                        comp_after_dedupe, comp_unique_sellers, price, shipping,
                        total_cost, market_value, discount_pct, deal_score,
                        verdict, seller_username, seller_feedback,
                        seller_feedback_count, item_url, image_url, item_end_date,
                        target_buy_price, target_price_hit, first_seen, last_seen,
                        listing_status, miss_count, ended_at, last_total_cost,
                        price_drop_amount, price_drop_pct, last_price_change_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(ebay_item_id) DO UPDATE SET
                        search_rule_id=excluded.search_rule_id,
                        linked_card_id=excluded.linked_card_id,
                        title=excluded.title,
                        series=excluded.series,
                        sticker_name=excluded.sticker_name,
                        sticker_number=excluded.sticker_number,
                        back_variant=excluded.back_variant,
                        product_type=excluded.product_type,
                        grader=excluded.grader,
                        grade=excluded.grade,
                        raw_condition=excluded.raw_condition,
                        quantity=excluded.quantity,
                        condition_flags=excluded.condition_flags,
                        comparison_key=excluded.comparison_key,
                        comparable_count=excluded.comparable_count,
                        comp_raw_clean=excluded.comp_raw_clean,
                        comp_after_dedupe=excluded.comp_after_dedupe,
                        comp_unique_sellers=excluded.comp_unique_sellers,
                        price=excluded.price,
                        shipping=excluded.shipping,
                        total_cost=excluded.total_cost,
                        market_value=excluded.market_value,
                        discount_pct=excluded.discount_pct,
                        deal_score=excluded.deal_score,
                        verdict=excluded.verdict,
                        seller_username=excluded.seller_username,
                        seller_feedback=excluded.seller_feedback,
                        seller_feedback_count=excluded.seller_feedback_count,
                        item_url=excluded.item_url,
                        image_url=excluded.image_url,
                        item_end_date=excluded.item_end_date,
                        target_buy_price=excluded.target_buy_price,
                        target_price_hit=excluded.target_price_hit,
                        last_seen=excluded.last_seen,
                        listing_status='active',
                        miss_count=0,
                        ended_at=NULL,
                        last_total_cost=ebay_listings.total_cost,
                        price_drop_amount=excluded.price_drop_amount,
                        price_drop_pct=excluded.price_drop_pct,
                        last_price_change_at=COALESCE(excluded.last_price_change_at, ebay_listings.last_price_change_at)
                    """,
                    (
                        item["ebay_item_id"], item["search_rule_id"],
                        item["linked_card_id"], item["title"], item["series"],
                        item["sticker_name"], item["sticker_number"],
                        item["back_variant"], item["product_type"], item["grader"],
                        item["grade"], item["raw_condition"], item["quantity"],
                        _flags_text(item["condition_flags"]),
                        item["comparison_key"], comparable_count,
                        int(comp_diag.get(item["comparison_key"], {}).get("raw_clean", 0)),
                        int(comp_diag.get(item["comparison_key"], {}).get("after_dedupe", 0)),
                        int(comp_diag.get(item["comparison_key"], {}).get("unique_sellers", 0)),
                        item["price"], item["shipping"], item["total_cost"], market, discount,
                        score, verdict, item["seller_username"],
                        item["seller_feedback"], item["seller_feedback_count"],
                        item["item_url"], item["image_url"], item["item_end_date"],
                        item["target_buy_price"], item["target_price_hit"],
                        previous["first_seen"] if previous else now, now, "active",
                        0, None, previous_total, drop_amount, drop_pct, last_change,
                    ),
                )

                row = conn.execute(
                    "SELECT id FROM ebay_listings WHERE ebay_item_id=?",
                    (item["ebay_item_id"],),
                ).fetchone()

                recent_same = conn.execute(
                    """
                    SELECT 1 FROM ebay_price_history
                    WHERE ebay_item_id=?
                      AND COALESCE(total_cost,-1)=COALESCE(?,-1)
                      AND COALESCE(market_value,-1)=COALESCE(?,-1)
                      AND observed_at >= datetime('now','-30 minutes')
                    LIMIT 1
                    """,
                    (item["ebay_item_id"], item["total_cost"], market),
                ).fetchone()
                if not recent_same:
                    conn.execute(
                        """
                        INSERT INTO ebay_price_history(
                            ebay_item_id, listing_id, observed_at, total_cost,
                            market_value, deal_score, verdict
                        ) VALUES (?,?,?,?,?,?,?)
                        """,
                        (
                            item["ebay_item_id"], row["id"] if row else None, now,
                            item["total_cost"], market, score, verdict,
                        ),
                    )

            conn.commit()

        # Stale/ended lifecycle.
        stale_after_row = conn.execute(
            "SELECT value FROM ebay_app_settings WHERE key='stale_after_misses'"
        ).fetchone()
        try:
            stale_after = max(1, int(stale_after_row["value"]))
        except Exception:
            stale_after = 3

        unseen = conn.execute(
            """
            SELECT id, miss_count, item_end_date
            FROM ebay_listings
            WHERE listing_status='active' AND last_seen < ?
            """,
            (started,),
        ).fetchall()
        current = datetime.now(timezone.utc)

        for row in unseen:
            misses = int(row["miss_count"] or 0) + 1
            status = "active"
            ended_at = None
            if row["item_end_date"]:
                try:
                    end_dt = datetime.fromisoformat(
                        str(row["item_end_date"]).replace("Z", "+00:00")
                    )
                    if end_dt <= current:
                        status = "ended"
                        ended_at = utcnow()
                except Exception:
                    pass
            if status == "active" and misses >= stale_after:
                status = "stale"
            conn.execute(
                "UPDATE ebay_listings SET miss_count=?, listing_status=?, ended_at=COALESCE(?,ended_at) WHERE id=?",
                (misses, status, ended_at, row["id"]),
            )
            if status in ("stale", "ended"):
                stale_marked += 1

        duration = round(time.monotonic() - timer, 2)
        conn.execute(
            """
            UPDATE ebay_scan_runs
            SET finished_at=?, status='success', searches_run=?, listings_seen=?,
                new_listings=?, price_drops=?, stale_marked=?, duration_seconds=?,
                raw_hits=?, accepted_hits=?, rejected_unrelated=?,
                rejected_conflict=?, rejected_multichoice=?, rejected_modern=?,
                rejected_product_filter=?, rejected_era_format=?
            WHERE id=?
            """,
            (
                utcnow(), searches_run, listings_seen, new_listings,
                price_drops, stale_marked, duration,
                raw_hits, accepted_hits, rejected_unrelated,
                rejected_conflict, rejected_multichoice, rejected_modern,
                rejected_product_filter, rejected_era_format, run_id,
            ),
        )
        conn.commit()
        return {
            "ok": True, "busy": False, "searches": searches_run,
            "listings": listings_seen, "new": new_listings,
            "price_drops": price_drops, "stale_marked": stale_marked,
            "duration": duration,
            "raw_hits": raw_hits,
            "accepted_hits": accepted_hits,
            "rejected_unrelated": rejected_unrelated,
            "rejected_conflict": rejected_conflict,
            "rejected_multichoice": rejected_multichoice,
            "rejected_modern": rejected_modern,
            "rejected_product_filter": rejected_product_filter,
            "rejected_era_format": rejected_era_format,
        }
    except Exception as exc:
        conn.execute(
            """
            UPDATE ebay_scan_runs SET finished_at=?, status='error',
                searches_run=?, listings_seen=?, new_listings=?, price_drops=?,
                stale_marked=?, duration_seconds=?, raw_hits=?, accepted_hits=?,
                rejected_unrelated=?, rejected_conflict=?,
                rejected_multichoice=?, rejected_modern=?, rejected_product_filter=?, rejected_era_format=?,
                error=? WHERE id=?
            """,
            (
                utcnow(), searches_run, listings_seen, new_listings, price_drops,
                stale_marked, round(time.monotonic() - timer, 2),
                raw_hits, accepted_hits, rejected_unrelated,
                rejected_conflict, rejected_multichoice, rejected_modern,
                rejected_product_filter, rejected_era_format, str(exc), run_id,
            ),
        )
        conn.commit()
        raise
    finally:
        conn.close()
        _scan_lock.release()
