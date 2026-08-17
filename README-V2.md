
# Wacky Nifty v2.0.0 — eBay Research Integration

This is an **upgrade overlay** for the existing `wacky-nifty` project.

It does not include or replace:
- `wacky_packages.db`
- your existing `static/style.css`
- card images
- `templates/card_detail.html`
- `templates/puzzles.html`
- desktop packaging files

## New functionality

- eBay Research dashboard
- database-backed Search Rules
- link an eBay search rule to an existing Wacky Packages card
- Series / sticker / back-variant parsing
- raw vs PSA/CGC/BGS/SGC separation
- lot detection
- condition/risk flags
- exact-comparable median pricing (minimum 3 current comps)
- BUY / GOOD / FAIR / PASS / RISK / UNPRICED scoring
- target buy prices
- watchlist and hide
- price history
- manual scanning
- optional scheduled scanning
- stale/ended listing lifecycle
- version shown as `v2.0.0`

## Important

The research tables are added to the existing `wacky_packages.db`.
Your existing `cards` and `series_puzzle_pieces` tables are not replaced.

Create `.env` from `.env.example` and add your eBay Production credentials.


## v2.0.1

- Replaced the long **Link to collection card** dropdown with a searchable autocomplete.
- Search by sticker name, Series, sticker number, or back color.
- Selecting a result stores the correct underlying `card.id`.


## v2.0.2

- Reworked **Link to collection card** search using the browser's native searchable datalist.
- Typing filters card choices by any text in the Series / number / sticker label.
- A visible **Selected:** status confirms the linked collection card.
- The hidden database card ID is updated only after a valid suggestion is chosen.


## v2.0.3

- Fixes collection-card links saving as `Not linked`.
- The searchable card label is now submitted with the form.
- Server-side fallback resolves `Series N #N · Sticker Name` back to the real
  `cards.id` when the browser does not populate the hidden ID.
- Linking no longer depends solely on JavaScript/datalist event behavior.


## v2.0.4

- Fixes first live eBay scan failure caused by numeric API values arriving as strings.
- Normalizes seller feedback percentage and feedback count in the eBay client.
- Adds defensive numeric coercion in the deal-scoring boundary.
- Prevents comparisons such as string `"99.8"` vs float `99.0`.


## v2.0.5

Critical comparable-matching fix:

- A linked Search Rule no longer assigns its card ID to every eBay result.
- Linked rules require the title to match the linked sticker name, or an exact
  Series + sticker-number identity.
- Unrelated results returned by eBay are discarded before scoring/comparable grouping.
- Generic "YOUR CHOICE", "YOU PICK", "CHOOSE ONE", etc. listings are flagged
  `MULTI-CHOICE` and excluded from normal clean comparable groups.
- Prevents unrelated Series/cards from creating false BUY scores.


## v2.0.6

Identity conflict and cleanup release:

- Explicit eBay Series conflicts reject a linked-card match.
- Explicit eBay sticker-number conflicts reject a linked-card match.
- The linked collection card no longer overwrites an explicitly different
  Series or sticker number from the eBay title.
- Existing active listings are revalidated against the linked rule at the
  start of every scan.
- Old contaminated rows are immediately moved to `invalid_match`.
- Invalid matches are excluded from the Research dashboard and visible on
  the Inactive page for audit/debugging.


## v2.0.7

Broader-but-auditable matching:

- Adds per-rule **Strict / Balanced / Broad** match modes.
- Strict uses the exact saved eBay query and requires the full normalized sticker name.
- Balanced broadens the outbound query slightly and allows strong token matches.
- Broad searches wider and allows looser name-token matches.
- Explicit Series/sticker-number conflicts remain hard rejects in every mode.
- Scan diagnostics show raw hits, accepted hits, unrelated rejects,
  identity-conflict rejects, and multi-choice rejects.
- Scan History stores those diagnostics for later tuning.


## v2.0.8

Rejected-hit audit release:

- Every rejected eBay result is persisted to `ebay_rejected_hits`.
- Stores:
  - rejection reason
  - original eBay title and URL
  - parsed Series / sticker number / sticker name
  - parsed back variant
  - raw vs graded identity
  - quantity
  - condition flags
  - linked collection card
  - name similarity
  - scan/run ID
- Adds a **Rejected Hits** page with filters by reason, scan, and text.
- Scan History links directly to the rejected hits from an individual scan.
- Makes matcher tuning evidence-driven without weakening safeguards.


## v2.0.9

Rejected Hits UI cleanup only; matching logic is unchanged.

- Wider eBay listing and Linked Target columns.
- Linked targets render as compact `S7 #18 · Grime Dog Food`.
- Stronger color-coded rejection badges.
- Adds a human-readable **Why rejected?** explanation:
  - `#28 ≠ #18`
  - `Series 3 ≠ 7`
  - choice/pick-one listing
  - insufficient title match
- Cleaner parsed identity display.
- Larger, fully visible **Open eBay** action button.


## v2.0.10

Corrects the numbering model for original Wacky Packages Series 1-16.

- `cards.sticker_number` remains the Vault's internal inventory/checklist order.
- An eBay title's `#NN` is retained as seller/catalog reference metadata.
- A differing eBay `#NN` is not a hard identity conflict for Series 1-16.
- Series remains a hard identity field.
- Sticker name remains the main title identity.
- Existing variant, grading, quantity, and risk safeguards are unchanged.
- Research results label the seller number as `eBay ref #NN`.
- Rejected Hits labels the Vault number as `internal #NN`.
- Old number-based audit records are labeled as historical rejects.
- The Scan column is compact instead of wrapping the full ISO timestamp.


## v2.0.11

Comparable-quality release. Identity matching rules are unchanged.

- Collapses near-identical listings from the same seller.
- Duplicate-family normalization ignores suffixes such as `*d2`, `DUP`,
  `DUPLICATE`, and `UPDATED`.
- Caps each seller at 2 listings per exact comparable group.
- Requires at least 3 clean comps and at least 2 unique sellers before a
  market value is calculated.
- Stores comp-quality diagnostics:
  - raw clean listing count
  - count after duplicate-family collapse
  - unique seller count
- Research UI shows comp count and seller diversity.

This reduces the chance that one high-volume seller controls the market median.


## v2.0.12

Market-column presentation cleanup only.

- Market value is now large and bold.
- Adds a small `MARKET` label above the value.
- Comp count and unique seller count are shown on separate lines.
- Deduplication diagnostics are smaller and visually secondary.
- Unpriced listings clearly show `MARKET —` with available comp diagnostics.
- No matching, scoring, or pricing logic changed.


## v2.0.13

Vintage-era safeguard release.

- Original Series 1-16 linked searches reject obvious modern/reprint material.
- Detects:
  - `Topps Chrome`
  - `reprint`
  - `reissue`
  - `reproduction`
  - `remake`
  - explicit modern years >= 1990
- Modern/reprint hits are excluded before comp building and pricing.
- Rejected Hits stores and displays:
  - modern/reprint reason
  - explicit years
  - modern product labels
- Scan diagnostics add `R:` for modern/reprint rejects.
- Existing Series/name/eBay-reference-number matching logic is unchanged.

Example:
- `1973 Topps Wacky Packages 3rd Series Spit & Spill` -> accepted
- `2014 Topps Chrome Wacky Packages Spit & Spill` -> rejected as modern/reprint


## v2.0.14

Raw-condition accuracy release.

Raw, ungraded vintage stickers are now classified into condition tiers:

- `NM/NMMT`
- `EX/EX-MT`
- `VG`
- `GOOD`
- `POOR/DAMAGED`
- `UNKNOWN`

The raw-condition tier is now part of the exact comparable key, so a `GOOD`
copy is not priced from `NM/NMMT` comps.

Graded cards remain grouped by grader + numeric grade and are not affected by
raw-condition parsing.

Research and Rejected Hits pages show the detected raw condition.

Existing Series/name/year/modern/reprint/quantity/back/grading safeguards remain
unchanged.


## v2.0.15

Research-results layout cleanup only.

- Caps the Listing column so long eBay titles stay inside their cell.
- Long titles wrap cleanly instead of overlapping Total / Market / Discount.
- Gives Total, Market, Discount, Seller, Identity, and Actions fixed breathing room.
- Adds horizontal scrolling on narrower windows rather than allowing columns to collide.
- No matching, scoring, condition, or pricing logic changed.


## v2.0.16

Emergency research-table layout repair.

- Reverts the brittle fixed-layout behavior introduced in v2.0.15.
- Uses an auto-layout table with a safe minimum width.
- Listing titles get a real 320-430px column and wrap normally.
- Total, Market, Discount, Seller, Identity, and Actions get guaranteed minimum widths.
- Narrow browser windows use horizontal scrolling instead of collapsing columns.
- No matching, scoring, condition, or pricing logic changed.


## v2.0.17

Small labeling and vintage-condition parser update.

- Search rule names below listings are now explicitly labeled `Rule: ...`.
- Raw-condition parsing recognizes `VGEX`, `VGEX+`, `VG/EX`, `VG/EX+`,
  `VG-EX`, `VG-EX+`, and `VG+`.
- Those shorthand grades map to the `VG` raw-condition tier.
- No pricing, matching, seller-deduplication, or scoring logic changed.


## v2.0.18

Search Rule product constraints.

Each rule can now specify:

- `Any`
- `Raw only`
- `Graded only`

For `Graded only`, optional constraints are available:

- Grader: Any / PSA / CGC / BGS / SGC
- Exact grade: optional numeric grade such as 8, 9, or 10

Listings that fail these rule constraints are rejected before comparable
grouping and pricing. They are stored in Rejected Hits with a `Product filter`
reason and a human-readable explanation.

Example:
- Rule: Graded only / PSA / 8
- Raw Duznt listing -> rejected
- CGC 8 Duznt -> rejected
- PSA 9 Duznt -> rejected
- PSA 8 Duznt -> accepted

Existing identity, condition, vintage-era, seller-deduplication, and pricing
logic remain unchanged.


## v2.0.19

Original-Series era / format safeguard.

For collection targets linked to original Series 1-16, listings are rejected
before pricing when they clearly represent a predecessor or non-standard format.

Detected safeguards include:

- 1967 / other explicit pre-1973 vintage years
- `DIE CUT`, `DIE-CUT`, `DIECUT`
- `PROOF`
- `TEST ISSUE`
- `TEST CARD`
- `TEST STICKER`
- `UNCUT`
- `FULL SHEET` / `UNCUT SHEET`

Modern years and modern/reprint products continue to use the existing
Modern / reprint safeguard.

Examples:

- `1973 Topps Wacky Packages Series 1 Duznt` -> eligible
- `1967 Wacky Packages Die Cut Duznt PSA 6` -> rejected Era / format
- `Wacky Packages Duznt Proof PSA 8` -> rejected Era / format
- `2014 Topps Chrome ...` -> rejected Modern / reprint

Rejected Hits now records and displays the era/format explanation.
Scan diagnostics use `E:` for Era / format rejects.

No market, seller-deduplication, raw-condition, or grading-bucket logic changed.


## v2.0.20

Complete original-series research.

Search Rules can now target either:

- Individual sticker / card
- Complete original series

For complete-series rules, choose Series 1 through Series 16.

The scanner recognizes phrases such as:

- `complete set`
- `complete series`
- `full set`
- `full series`
- `complete run`

and excludes misleading/non-complete listings such as:

- `complete your set`
- `build your set`
- `you pick`
- `u pick`
- `pick one`
- `your choice`
- `individual cards`
- `single cards`

Complete-series listings receive their own comparable group:
`COMPLETE_SERIES:<series>|COND:<condition>`.

This keeps complete sets completely separate from individual sticker pricing.


## v2.0.21

Complete-Series scan crash fix.

v2.0.20 introduced complete-Series parsing but its normalized parser result did
not include every field consumed by the common scanner/upsert path. This caused:

`eBay scan failed: 'confidence'`

v2.0.21 makes complete-Series parser results structurally compatible with
individual-card parser results, including:

- confidence
- confidence_score
- condition flags
- quantity
- raw condition
- comparison key
- identity conflict flags
- modern / era safeguard metadata

Complete-Series identity rendering is also cleaned up so it displays as
`Complete Series N` rather than card-number metadata.

No changes were made to individual-card matching or pricing logic.


## v2.0.22

Complete-Series shared-scanner compatibility fix.

v2.0.21 fixed the missing `confidence` field, but the common persistence path
also expects several optional listing fields that individual-card scans normally
populate implicitly.

v2.0.22 explicitly normalizes those fields for every accepted listing:

- `linked_card_id`
- `target_buy_price`
- `target_price_hit`
- `item_end_date`
- `seller_feedback_count`
- `product_filter_reject`

Complete-Series rules correctly use `linked_card_id = NULL`.

This prevents the `eBay scan failed: 'linked_card_id'` crash and hardens the
shared scanner path against further optional-key failures.


## v2.0.23

Complete-Series era safeguard fix.

v2.0.20-v2.0.22 correctly distinguished complete sets from individual cards,
but complete-Series parsing did not apply the same vintage-era safeguards used
by individual Series 1-16 research.

This allowed listings such as:

- `2004 Wacky Packages All New Series 1 Complete Set`

to be treated as original 1973 Series 1 comps.

v2.0.23 fixes that.

Complete original-Series rules now reject:

- explicit modern years (1990+), including 2004
- Topps Chrome
- reprint / reissue / reproduction / remake wording
- pre-1973 predecessor years
- die-cut / proof / test issue / uncut / sheet formats

Examples:

- `1973 Wacky Packages Series 1 Complete Set` -> accepted
- `2004 Wacky Packages All New Series 1 Complete Set` -> rejected Modern / reprint
- `1967 Wacky Packages Die Cut Complete Set` -> rejected Era / format
- `1974 Wacky Packages 7th Series Full Set` -> accepted

No individual-card matching or pricing logic changed.


## v2.0.24

Complete-Series stale-listing cleanup.

The v2.0.23 era safeguard correctly rejected modern complete-set hits during
new scans, but listings accepted by older versions could remain marked
`active` in SQLite and continue to appear on the Research page.

v2.0.24 revalidates every currently-active listing attached to a
Complete-Series rule before each scan.

Listings that no longer satisfy the current rule are immediately changed to:

`listing_status = invalid_match`

Examples automatically retired from an original Series 1 rule:

- 2004 All New Series 1
- 2004 ANS1
- Flashback Series 1
- modern/reprint listings
- wrong-Series complete sets
- product-filter mismatches

The revalidation uses the same current parser and product constraints as new
scan results. Individual-card rule behavior is unchanged.


## v2.0.25

Fixes stale complete-Series revalidation on existing databases.

v2.0.24 attempted to update an `updated_at` column on `ebay_listings`, but
that table does not have that column in existing installations.

The revalidation now only changes:

`listing_status = invalid_match`

This fixes:

`eBay scan failed: no such column: updated_at`

No matching, scoring, pricing, or rule logic changed.


## v2.0.26

Complete-Series product-line safeguard.

Original Series 1-16 complete-set rules now reject non-original product lines
that reuse Series numbering even when the seller title does not include a year.

Rejected as Modern / reprint:

- Flashback
- Foil
- Halo
- Vending
- Special Edition
- All New Series
- ANS / ANS1 / ANS2...
- Topps Chrome / Chrome
- Reprint
- Reissue
- Reproduction
- Remake

Examples:

- `1973 Wacky Packages Series 1 Complete Set` -> accepted
- `Wacky Packages Original Series 1 Complete Set` -> accepted
- `Wacky Packages Flashback Series 1 Complete Set` -> rejected
- `Wacky Packages Foil Halo Vending Special Edition Series 1 Complete Set` -> rejected
- `2004 Wacky Packages All New Series 1 Complete Set` -> rejected

This prevents modern/reissue product lines from contaminating original Series
1-16 complete-set market values.


## v2.0.27

Complete-Series Minis / incomplete-set safeguard.

Original Series 1-16 complete-set rules now reject additional non-original
product lines:

- Minis
- Miniatures
- Mini Figures
- Figures

They also reject listings that explicitly are not complete:

- Near complete / nearly complete
- Almost complete
- Partial set
- Incomplete
- Missing cards/stickers/pieces, including `Missing 2 Cards`
- `X of Y` wording such as `37 of 66`

Examples:

- `Wacky Packages Minis Series 1 NEAR COMPLETE SET Lot 37 of 66 Figures` -> rejected
- `Wacky Packages Minis Series 1 Lot 48 of 66 Figures + Stickers` -> rejected
- `1973 Wacky Packages Series 1 Complete Set Missing 2 Cards` -> rejected
- `1973 Wacky Packages Series 1 Complete Set` -> accepted

Existing stale-row revalidation automatically removes older accepted rows after
the next scan.


## v2.0.28

Complete-Series back-variation safeguard.

Complete original Series 1-16 listings now detect:

- White Back / White Backs
- Tan Back / Tan Backs

The back type is included in the comparable key:

`COMPLETE_SERIES:<series>|BACK:<white|tan|UNKNOWN>|COND:<condition>|QTY:1`

This prevents a White Back complete set from being priced from Tan Back
complete-set comps.

The Research page now shows the detected back type for Complete-Series rows.

Examples:

- `1973 Topps Wacky Packages Series 1 Complete Set 30/30 White Back`
  -> Complete Series 1 / White back
- `1973 Topps Wacky Packages Series 1 Complete Set Tan Backs`
  -> Complete Series 1 / Tan back
- no back wording
  -> Back UNKNOWN

No single-card matching or pricing logic changed.


## v2.0.29

Complete-Series condition parsing.

Complete original-Series listings now use an explicit set-condition parser with
these conservative tiers:

- `NM/NMMT`
- `EX/EX-MT`
- `VG`
- `GOOD`
- `POOR/DAMAGED`
- `UNKNOWN`

Recognized examples include:

- NM, NM+, NMMT, NM/MT, Near Mint, Mint
- EX, EX+, EX/MT, EX-MT, Excellent
- VG, VG+, VGEX, VGEX+, VG/EX, Very Good
- Good / Good Condition
- Poor, Damaged, Creased, Torn, Trimmed, Writing, Marked, Stained

Vague wording such as `nice`, `clean`, `beautiful`, or `great` intentionally
remains UNKNOWN.

Complete-Series comparable keys already include condition, so the detected tier
now directly separates market comps.

The Research page now displays:

`Condition · EX/EX-MT`

instead of the generic `Raw · EX/EX-MT`.


## v2.0.30

Wacky Packages condition-display cleanup.

eBay's generic listing condition (normally `Used` for vintage Wacky Packages)
is no longer shown in the research UI because it does not provide useful
collector-grade information.

The app continues to store eBay listing condition internally if supplied by
the API, but the visible collector condition remains:

- `NM/NMMT`
- `EX/EX-MT`
- `VG`
- `GOOD`
- `POOR/DAMAGED`
- `UNKNOWN`

No matching, pricing, scoring, filtering, or database logic changed.
