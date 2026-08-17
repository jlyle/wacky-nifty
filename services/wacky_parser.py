
import re

BACK_PATTERNS = [
    ("red ludlow", r"\bRED\s+LUDLOW\b"),
    ("black ludlow", r"\bBLACK\s+LUDLOW\b"),
    ("cloth", r"\bCLOTH\b"),
    ("tan", r"\bTAN\s+BACK\b|\bTANBACK\b"),
    ("white", r"\bWHITE\s+BACK\b|\bWHITEBACK\b"),
]

CONDITION_FLAGS = {
    "MODERN/REPRINT": r"\bTOPPS\s+CHROME\b|\bREPRINT\b|\bREISSUE\b|\bREISSUED\b|\bREPRODUCTION\b|\bREMAKE\b",
    "MULTI-CHOICE": r"\bYOUR\s+CHOICE\b|\bYOU\s+CHOOSE\b|\bCHOOSE\s+ONE\b|\bPICK\s+ONE\b|\bU\s+PICK\b|\bYOU\s+PICK\b",
    "DAMAGED": r"\bDAMAGED\b|\bCREASED\b|\bCREASE\b|\bTORN\b",
    "TRIMMED": r"\bTRIMMED\b",
    "WRITING": r"\bWRITING\b|\bMARKED\b",
    "READ DESCRIPTION": r"\bREAD\s+(?:THE\s+)?DESCRIPTION\b|\bREAD\b",
    "REPRINT": r"\bREPRINT\b|\bREPRODUCTION\b|\bREPRO\b",
}

def normalize(text):
    text = (text or "").upper().replace("’", "'")
    text = re.sub(r"[^A-Z0-9#/' .+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def detect_series(title):
    t = normalize(title)
    patterns = [
        r"\bSERIES\s*(1[0-6]|[1-9])\b",
        r"\b(1[0-6]|[1-9])(?:ST|ND|RD|TH)\s+SERIES\b",
        r"\bS(?:ERIES)?\s*#?\s*(1[0-6]|[1-9])\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, t)
        if m:
            return int(m.group(1))
    return None

def detect_sticker_number(title):
    t = normalize(title)
    for pattern in [
        r"\bSTICKER\s*#\s*(\d{1,3})\b",
        r"\bCARD\s*#\s*(\d{1,3})\b",
        r"(?<!\w)#\s*(\d{1,3})\b",
    ]:
        m = re.search(pattern, t)
        if m:
            return int(m.group(1))
    return None

def detect_back_variant(title):
    t = normalize(title)
    for name, pattern in BACK_PATTERNS:
        if re.search(pattern, t):
            return name
    return None

def detect_grade(title):
    t = normalize(title)
    for grader in ("PSA", "CGC", "BGS", "SGC"):
        m = re.search(rf"\b{grader}\s*(?:GEM\s*MINT\s*)?(\d+(?:\.\d+)?)\b", t)
        if m:
            return grader, float(m.group(1))
    return None, None

def detect_quantity(title):
    t = normalize(title)
    for pattern in [
        r"\bLOT\s+OF\s+(\d+)\b",
        r"\bSET\s+OF\s+(\d+)\b",
        r"\b(\d+)\s*CARD\s+LOT\b",
        r"\b(\d+)\s*STICKER\s+LOT\b",
        r"\bPAIR\b",
    ]:
        m = re.search(pattern, t)
        if m:
            if m.group(0) == "PAIR":
                return 2
            try:
                return max(1, int(m.group(1)))
            except Exception:
                pass
    return 1

def detect_condition_flags(title):
    t = normalize(title)
    return [name for name, pattern in CONDITION_FLAGS.items() if re.search(pattern, t)]


NAME_STOPWORDS = {
    "THE", "AND", "OF", "A", "AN", "PRODUCT", "BRAND",
}

def meaningful_tokens(text):
    return [
        token for token in normalize(text).split()
        if len(token) >= 2 and token not in NAME_STOPWORDS
    ]

def title_name_similarity(title, sticker_name):
    title_n = normalize(title)
    name_n = normalize(sticker_name)
    if not name_n:
        return 0.0
    if name_n in title_n:
        return 1.0

    wanted = meaningful_tokens(sticker_name)
    if not wanted:
        return 0.0

    title_tokens = set(meaningful_tokens(title))
    matched = sum(1 for token in wanted if token in title_tokens)
    return matched / len(wanted)

def title_contains_name(title, sticker_name, mode="balanced"):
    if not sticker_name:
        return False

    mode = (mode or "balanced").strip().lower()
    title_n = normalize(title)
    name_n = normalize(sticker_name)

    if mode == "strict":
        # Strict means the full normalized sticker name must appear.
        return bool(name_n and name_n in title_n)

    similarity = title_name_similarity(title, sticker_name)

    if mode == "broad":
        return similarity >= 0.60

    return similarity >= 0.75


def detect_explicit_years(title):
    t = normalize(title)
    years = []
    for match in re.finditer(r"\b(19\d{2}|20\d{2})\b", t):
        try:
            years.append(int(match.group(1)))
        except ValueError:
            pass
    return years

def detect_modern_issue(title, linked_card=None):
    """
    Original Wacky Packages Series 1-16 are vintage-era material.
    Explicit modern years (>= 1990) or modern/reprint product wording
    reject those listings from vintage comparable groups.
    """
    t = normalize(title)
    flags = []

    if re.search(r"\bTOPPS\s+CHROME\b", t):
        flags.append("TOPPS CHROME")
    if re.search(r"\bREPRINT\b|\bREISSUE\b|\bREISSUED\b|\bREPRODUCTION\b|\bREMAKE\b", t):
        flags.append("REPRINT/REISSUE")

    years = detect_explicit_years(title)
    modern_years = [y for y in years if y >= 1990]

    original_series = False
    if linked_card:
        try:
            original_series = 1 <= int(linked_card["series"]) <= 16
        except Exception:
            original_series = False

    is_modern = bool(original_series and (modern_years or flags))
    return {
        "is_modern": is_modern,
        "years": years,
        "modern_years": modern_years,
        "labels": flags,
    }



ORIGINAL_SERIES_FORMAT_PATTERNS = [
    ("DIE CUT", r"\bDIE[\s-]*CUT\b|\bDIECUT\b"),
    ("PROOF", r"\bPROOF\b"),
    ("TEST ISSUE", r"\bTEST\s+ISSUE\b|\bTEST\s+CARD\b|\bTEST\s+STICKER\b"),
    ("UNCUT", r"\bUNCUT\b"),
    ("SHEET", r"\bFULL\s+SHEET\b|\bUNCUT\s+SHEET\b"),
]

def detect_original_series_format_issue(title, linked_card=None):
    """
    Linked original Series 1-16 targets represent the 1973-1977 sticker era.
    Reject explicit predecessor/non-standard formats even if the target name
    itself matches.
    """
    t = normalize(title)
    labels = []

    original_series = False
    if linked_card:
        try:
            original_series = 1 <= int(linked_card["series"]) <= 16
        except Exception:
            original_series = False

    if not original_series:
        return {
            "is_issue": False,
            "labels": [],
            "years": detect_explicit_years(title),
            "off_era_years": [],
            "detail": None,
        }

    for label, pattern in ORIGINAL_SERIES_FORMAT_PATTERNS:
        if re.search(pattern, t):
            labels.append(label)

    years = detect_explicit_years(title)

    # Original numbered Wacky Packages Series 1-16 are 1973-1977-era material.
    # A seller may list no year at all; only explicit off-era years are rejected.
    off_era_years = [year for year in years if year < 1973 or year > 1977]

    # Modern years are already handled by the modern/reprint safeguard.
    # Keep this category focused on predecessor/non-standard vintage formats.
    vintage_off_era = [year for year in off_era_years if year < 1990]

    is_issue = bool(labels or vintage_off_era)

    detail_parts = []
    if labels:
        detail_parts.append(", ".join(labels))
    if vintage_off_era:
        detail_parts.append("off-era year " + ", ".join(str(y) for y in vintage_off_era))

    return {
        "is_issue": is_issue,
        "labels": labels,
        "years": years,
        "off_era_years": vintage_off_era,
        "detail": " · ".join(detail_parts) if detail_parts else None,
    }


COMPLETE_SERIES_POSITIVE_PATTERNS = [
    r"\bCOMPLETE\s+SET\b",
    r"\bCOMPLETE\s+SERIES\b",
    r"\bFULL\s+SET\b",
    r"\bFULL\s+SERIES\b",
    r"\bCOMPLETE\s+RUN\b",
]

COMPLETE_SERIES_NEGATIVE_PATTERNS = [
    r"\bCOMPLETE\s+YOUR\s+SET\b",
    r"\bBUILD\s+YOUR\s+SET\b",
    r"\bYOU\s+PICK\b",
    r"\bU\s+PICK\b",
    r"\bPICK\s+ONE\b",
    r"\bYOUR\s+CHOICE\b",
    r"\bINDIVIDUAL\s+CARDS?\b",
    r"\bSINGLE\s+CARDS?\b",
]

def detect_complete_series(title):
    t = normalize(title)

    if any(re.search(pattern, t) for pattern in COMPLETE_SERIES_NEGATIVE_PATTERNS):
        return False

    return any(re.search(pattern, t) for pattern in COMPLETE_SERIES_POSITIVE_PATTERNS)

def detect_series_number(title):
    t = normalize(title)

    patterns = [
        r"\bSERIES\s*#?\s*(1[0-6]|[1-9])\b",
        r"\b(1[0-6]|[1-9])(?:ST|ND|RD|TH)\s+SERIES\b",
        r"\bS(1[0-6]|[1-9])\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, t)
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                pass

    return None







def detect_complete_series_condition(title):
    """
    Conservative condition parsing for complete original-Series sets.

    Only explicit seller condition wording is used. Vague adjectives such as
    "nice", "clean", "beautiful", or "great" intentionally stay UNKNOWN.
    """
    t = normalize(title)

    if re.search(
        r"\bPOOR\b|\bDAMAGED\b|\bHEAVILY\s+WORN\b|\bCREASED\b|\bCREASE\b|"
        r"\bTORN\b|\bTRIMMED\b|\bWRITING\b|\bMARKED\b|\bSTAINED\b|\bSTAINS?\b",
        t,
    ):
        return "POOR/DAMAGED"

    if re.search(
        r"\bVG/EX\+?\b|\bVG-EX\+?\b|\bVGEX\+?\b|\bVERY\s+GOOD\b|\bVG\+?\b",
        t,
    ):
        return "VG"

    if re.search(
        r"\bEX/MT\b|\bEX-MT\b|\bEXMT\b|\bEXCELLENT\b|\bEX\+?\b",
        t,
    ):
        return "EX/EX-MT"

    if re.search(
        r"\bNMMT\b|\bNM/MT\b|\bNM-MT\b|\bNEAR\s+MINT\b|\bMINT\b|\bNM\+?\b",
        t,
    ):
        return "NM/NMMT"

    if re.search(r"\bGOOD\s+CONDITION\b|\bGOOD\b", t):
        return "GOOD"

    return "UNKNOWN"

def detect_complete_series_back(title):
    t = normalize(title)

    if re.search(r"\bWHITE\s+BACKS?\b|\bWHITEBACKS?\b", t):
        return "white"

    if re.search(r"\bTAN\s+BACKS?\b|\bTANBACKS?\b", t):
        return "tan"

    return None


def parse_complete_series_listing(title, target_series=None):
    series = detect_series_number(title)
    is_complete = detect_complete_series(title)
    flags = detect_condition_flags(title)
    raw_condition = detect_complete_series_condition(title)
    quantity = detect_quantity(title)
    back_variant = detect_complete_series_back(title)

    years = detect_explicit_years(title)
    modern_years = [y for y in years if y >= 1990]
    pre_original_years = [y for y in years if y < 1973]

    t = normalize(title)

    non_original_product_patterns = [
        ("FLASHBACK", r"\bFLASHBACK\b"),
        ("FOIL", r"\bFOIL\b"),
        ("HALO", r"\bHALO\b"),
        ("VENDING", r"\bVENDING\b"),
        ("SPECIAL EDITION", r"\bSPECIAL\s+EDITION\b"),
        ("ALL NEW SERIES", r"\bALL\s+NEW\s+SERIES\b"),
        ("ANS", r"\bANS\s*#?\s*\d*\b|\{ANS\d+\}"),
        ("TOPPS CHROME", r"\bTOPPS\s+CHROME\b"),
        ("CHROME", r"\bCHROME\b"),
        ("MINIS", r"\bMINIS\b|\bMINIATURES?\b|\bMINI\s+FIGURES?\b"),
        ("FIGURES", r"\bFIGURES?\b"),
        ("REPRINT/REISSUE", r"\bREPRINT\b|\bREISSUE\b|\bREISSUED\b|\bREPRODUCTION\b|\bREMAKE\b"),
    ]

    modern_labels = []
    for label, product_pattern in non_original_product_patterns:
        if re.search(product_pattern, t):
            modern_labels.append(label)

    is_modern_issue = bool(modern_years or modern_labels)

    incomplete_patterns = [
        ("NEAR COMPLETE", r"\bNEAR(?:LY)?\s+COMPLETE\b"),
        ("ALMOST COMPLETE", r"\bALMOST\s+COMPLETE\b"),
        ("PARTIAL SET", r"\bPARTIAL\s+SET\b"),
        ("INCOMPLETE", r"\bINCOMPLETE\b"),
        ("MISSING ITEMS", r"\bMISSING(?:\s+\d+)?\s+(?:CARD|CARDS|STICKER|STICKERS|PIECE|PIECES)\b"),
        ("X OF Y", r"\b\d+\s+OF\s+\d+\b"),
    ]

    incomplete_labels = []
    for label, incomplete_pattern in incomplete_patterns:
        if re.search(incomplete_pattern, t):
            incomplete_labels.append(label)

    is_incomplete_set = bool(incomplete_labels)

    if is_incomplete_set:
        is_complete = False

    era_labels = []
    for label, fmt_pattern in ORIGINAL_SERIES_FORMAT_PATTERNS:
        if re.search(fmt_pattern, t):
            era_labels.append(label)

    is_era_format_issue = bool(pre_original_years or era_labels)

    era_detail_parts = []
    if era_labels:
        era_detail_parts.append(", ".join(era_labels))
    if pre_original_years:
        era_detail_parts.append(
            "off-era year " + ", ".join(str(y) for y in pre_original_years)
        )
    era_format_detail = " · ".join(era_detail_parts) if era_detail_parts else None

    series_conflict = (
        target_series is not None
        and series is not None
        and int(series) != int(target_series)
    )

    match = bool(
        is_complete
        and not series_conflict
        and not is_modern_issue
        and not is_era_format_issue
        and not is_incomplete_set
    )

    if target_series is not None and series is None:
        match = bool(
            is_complete
            and not is_modern_issue
            and not is_era_format_issue
            and not is_incomplete_set
        )

    if is_modern_issue:
        match_reason = "modern_issue"
    elif is_era_format_issue:
        match_reason = "era_format_issue"
    elif is_incomplete_set:
        match_reason = "not_complete_series"
    elif series_conflict:
        match_reason = "identity_conflict"
    elif match:
        match_reason = "complete_series_match"
    else:
        match_reason = "not_complete_series"

    resolved_series = series or target_series
    back_key = back_variant or "UNKNOWN"

    comparison_key = (
        f"COMPLETE_SERIES:{resolved_series}"
        f"|BACK:{back_key}"
        f"|COND:{raw_condition}|QTY:{quantity}"
    )

    return {
        "series": resolved_series,
        "sticker_number": None,
        "ebay_catalog_number": None,
        "sticker_name": f"Complete Series {resolved_series}" if resolved_series else "Complete Series",
        "back_variant": back_variant,
        "product_type": "complete_series",
        "grader": None,
        "grade": None,
        "raw_condition": raw_condition,
        "quantity": quantity,
        "condition_flags": flags,
        "confidence": "HIGH" if match and resolved_series else "MEDIUM",
        "confidence_score": 95 if match and resolved_series else 75,
        "comparison_key": comparison_key,
        "linked_match": match,
        "match_reason": match_reason,
        "name_similarity": 1.0 if match else 0.0,
        "series_conflict": series_conflict,
        "number_conflict": False,
        "is_complete_series": is_complete,
        "is_incomplete_set": is_incomplete_set,
        "incomplete_labels": incomplete_labels,
        "is_modern_issue": is_modern_issue,
        "explicit_years": years,
        "modern_years": modern_years,
        "modern_labels": modern_labels,
        "is_era_format_issue": is_era_format_issue,
        "era_format_labels": era_labels,
        "off_era_years": pre_original_years,
        "era_format_detail": era_format_detail,
    }

RAW_CONDITION_PATTERNS = [
    ("NM/NMMT", [
        r"\bNMMT\b",
        r"\bNM/MT\b",
        r"\bNM-MT\b",
        r"\bNEAR\s+MINT\b",
        r"\bMINT\b",
        r"\bNM\b",
    ]),
    ("EX/EX-MT", [
        r"\bEX/MT\b",
        r"\bEX-MT\b",
        r"\bEXMT\b",
        r"\bEXCELLENT\b",
        r"\bEX\b",
    ]),
    ("VG", [
        r"\bVG/EX\b",
        r"\bVG-EX\b",
        r"\bVERY\s+GOOD\b",
        r"\bVG\b",
    ]),
    ("GOOD", [
        r"\bGOOD\s+CONDITION\b",
        r"\bGOOD\b",
        r"\bG\b",
    ]),
    ("POOR/DAMAGED", [
        r"\bPOOR\b",
        r"\bDAMAGED\b",
        r"\bCREASED\b",
        r"\bCREASE\b",
        r"\bTORN\b",
        r"\bTRIMMED\b",
        r"\bWRITING\b",
        r"\bMARKED\b",
    ]),
]

def detect_raw_condition(title, grader=None):
    if grader:
        return None

    t = normalize(title)

    # Evaluate worse/more specific condition language first where ambiguity
    # could exist, while preserving the desired named buckets.
    if re.search(r"\bPOOR\b|\bDAMAGED\b|\bCREASED\b|\bCREASE\b|\bTORN\b|\bTRIMMED\b|\bWRITING\b|\bMARKED\b", t):
        return "POOR/DAMAGED"

    if re.search(
        r"\bVG/EX\+?\b|\bVG-EX\+?\b|\bVGEX\+?\b|\bVERY\s+GOOD\b|\bVG\+?\b",
        t,
    ):
        return "VG"

    if re.search(r"\bEX/MT\b|\bEX-MT\b|\bEXMT\b|\bEXCELLENT\b|\bEX\b", t):
        return "EX/EX-MT"

    if re.search(r"\bNMMT\b|\bNM/MT\b|\bNM-MT\b|\bNEAR\s+MINT\b|\bMINT\b|\bNM\b", t):
        return "NM/NMMT"

    if re.search(r"\bGOOD\s+CONDITION\b|\bGOOD\b", t):
        return "GOOD"

    return "UNKNOWN"

def parse_listing(title, linked_card=None, match_mode="balanced"):
    series = detect_series(title)
    sticker_number = detect_sticker_number(title)
    back_variant = detect_back_variant(title)
    grader, grade = detect_grade(title)
    raw_condition = detect_raw_condition(title, grader)
    quantity = detect_quantity(title)
    flags = detect_condition_flags(title)
    modern_issue = detect_modern_issue(title, linked_card)
    era_format_issue = detect_original_series_format_issue(title, linked_card)

    if modern_issue["is_modern"] and "MODERN/REPRINT" not in flags:
        flags.append("MODERN/REPRINT")
    if era_format_issue["is_issue"] and "ERA/FORMAT" not in flags:
        flags.append("ERA/FORMAT")

    sticker_name = None
    linked_card_id = None
    linked_match = False
    match_reason = "unlinked"

    if linked_card:
        # A linked rule does not make every search hit the linked card.
        # Explicit Series / sticker-number conflicts in the eBay title are
        # authoritative rejection signals.
        series_conflict = (
            series is not None
            and int(series) != int(linked_card["series"])
        )
        # cards.sticker_number is the Vault's internal inventory order
        # for original Series 1-16. eBay sellers may use a different
        # checklist/catalog number, so retain their #NN as metadata without
        # treating it as an identity conflict.
        internal_order_series = 1 <= int(linked_card["series"]) <= 16
        number_conflict = (
            not internal_order_series
            and sticker_number is not None
            and int(sticker_number) != int(linked_card["sticker_number"])
        )

        if modern_issue["is_modern"]:
            linked_match = False
            match_reason = "modern_issue"
        elif era_format_issue["is_issue"]:
            linked_match = False
            match_reason = "era_format_issue"
        elif series_conflict or number_conflict:
            linked_match = False
            match_reason = "identity_conflict"
        elif title_contains_name(title, linked_card["sticker_name"], match_mode):
            linked_match = True
            match_reason = "name_match"
            linked_card_id = linked_card["id"]
            sticker_name = linked_card["sticker_name"]
            series = series or linked_card["series"]
            sticker_number = sticker_number or linked_card["sticker_number"]
        elif (
            series == linked_card["series"]
            and sticker_number == linked_card["sticker_number"]
        ):
            linked_match = True
            match_reason = "series_number_match"
            linked_card_id = linked_card["id"]
            sticker_name = linked_card["sticker_name"]

    product_type = "graded" if grader else "raw"
    back_key = back_variant or "unspecified"
    identity = f"CARD:{linked_card_id}" if linked_card_id else (
        f"S{series}:#{sticker_number}" if series and sticker_number else "UNRESOLVED"
    )
    grade_key = f"{grader}:{grade:g}" if grader and grade is not None else "RAW"
    condition_key = raw_condition if not grader else "GRADED"

    comparison_key = (
        f"{identity}|{product_type}|{grade_key}|COND:{condition_key}|BACK:{back_key}|QTY:{quantity}"
    )

    confidence = 0
    if linked_card_id and sticker_name:
        confidence += 65
    elif series and sticker_number:
        confidence += 50
    if back_variant:
        confidence += 10
    if grader:
        confidence += 15
    if quantity == 1:
        confidence += 5

    return {
        "series": series,
        "sticker_number": sticker_number,
        "ebay_catalog_number": sticker_number,
        "sticker_name": sticker_name,
        "linked_card_id": linked_card_id,
        "linked_match": linked_match,
        "match_reason": match_reason,
        "is_modern_issue": modern_issue["is_modern"],
        "explicit_years": modern_issue["years"],
        "modern_years": modern_issue["modern_years"],
        "modern_labels": modern_issue["labels"],
        "is_era_format_issue": era_format_issue["is_issue"],
        "era_format_labels": era_format_issue["labels"],
        "off_era_years": era_format_issue["off_era_years"],
        "era_format_detail": era_format_issue["detail"],
        "name_similarity": round(title_name_similarity(title, linked_card["sticker_name"]), 3) if linked_card else None,
        "series_conflict": series_conflict if linked_card else False,
        "number_conflict": number_conflict if linked_card else False,
        "back_variant": back_variant,
        "product_type": product_type,
        "grader": grader,
        "grade": grade,
        "raw_condition": raw_condition,
        "quantity": quantity,
        "condition_flags": flags,
        "comparison_key": comparison_key,
        "confidence": min(confidence, 100),
    }
