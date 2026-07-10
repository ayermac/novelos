"""v6.10.19: Migrate deprecated ChapterBrief fields → new fields.

Reads chapter_briefs.brief_data JSON (supports both flat and nested tier1/tier2
shapes), merges deprecated field values into new v6.10.18 target fields.

Usage:
    python -m novel_factory.db.data_migrations.001_v6_10_19_chapter_brief_field_migration --db-path <db> [--dry-run]

The script:
  1. Backs up original brief_data to _chapter_briefs_migration_backup table
  2. Parses each brief_data JSON
  3. Merges old fields into conflict / notes / payoff_points / required_beats
  4. Writes back (unless --dry-run)

Rollback: copy rows from _chapter_briefs_migration_backup back to chapter_briefs.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# ── Field mapping ────────────────────────────────────────────────────

# Fields merged into NOTES (free-text sectioned)
NOTES_MERGE_FIELDS = [
    "protagonist_agency", "payoff_evidence_plan", "upgrade_or_skill_use",
    "character_arc_moves", "mystery_actions", "new_debts_allowed",
    "scene_count_target", "opening_hook", "quality_threshold_overrides",
    "supporting_mechanisms_used", "new_mechanisms_allowed",
    "drift_risks", "contract_checklist",
    "pressure_budget", "payoff_budget",
]

# Fields merged into PAYOFF_POINTS (JSON array)
PAYOFF_MERGE_FIELDS = ["reader_payoff", "primary_payoff", "payoff_evidence_plan"]

# Fields merged into CONFLICT
CONFLICT_MERGE_FIELDS = ["conflict_actions", "core_loop_target"]

# Fields merged into REQUIRED_BEATS
BEATS_MERGE_FIELDS = ["ledger_debts_to_pay", "scene_count_target"]

# Tier1 fields that may appear in nested shape
TIER1_KEYS = {"chapter_goal", "reader_payoff", "protagonist_agency",
              "forbidden_moves", "core_loop_target", "primary_payoff",
              "payoff_evidence_plan"}

TIER2_KEYS = {"pressure_budget", "payoff_budget", "upgrade_or_skill_use",
              "character_arc_moves", "mystery_actions", "conflict_actions",
              "ledger_debts_to_pay", "new_debts_allowed", "scene_count_target",
              "opening_hook", "ending_hook", "quality_threshold_overrides",
              "supporting_mechanisms_used", "new_mechanisms_allowed",
              "drift_risks", "contract_checklist"}


# ── Core logic ────────────────────────────────────────────────────────

@dataclass
class MigrationReport:
    total: int = 0
    skipped: int = 0
    migrated: int = 0
    details: list[str] = field(default_factory=list)


def _flatten_brief(brief_data: dict) -> dict:
    """Flatten nested {tier1, tier2} into flat dict with all field keys."""
    flat = {}
    # Copy tier1 fields
    tier1 = brief_data.get("tier1", {})
    if isinstance(tier1, dict):
        for k in TIER1_KEYS:
            if k in tier1:
                flat[k] = tier1[k]
        for k, v in tier1.items():
            if k not in flat:
                flat[k] = v
    # Copy tier2 fields
    tier2 = brief_data.get("tier2", {})
    if isinstance(tier2, dict):
        for k in TIER2_KEYS:
            if k in tier2:
                flat[k] = tier2[k]
        for k, v in tier2.items():
            if k not in flat:
                flat[k] = v
    # Copy flat fields (for non-nested briefs)
    for k, v in brief_data.items():
        if k not in ("tier1", "tier2") and k not in flat:
            flat[k] = v
    return flat


def _build_notes_section(flat: dict) -> str:
    """Build notes content by appending non-empty deprecated fields."""
    sections = []
    existing_notes = str(flat.get("notes") or "").strip()
    if existing_notes:
        sections.append(existing_notes)

    for field in NOTES_MERGE_FIELDS:
        value = flat.get(field)
        if _has_content(value):
            formatted = _format_value(value)
            sections.append(f"\n--- {field} ---\n{formatted}")
    return "\n".join(sections).strip()


def _build_payoff_points(flat: dict) -> list[str]:
    """Build payoff_points list by collecting non-empty values."""
    existing = flat.get("payoff_points", [])
    if isinstance(existing, str):
        try:
            existing = json.loads(existing)
        except (json.JSONDecodeError, TypeError):
            existing = [existing] if existing else []
    if not isinstance(existing, list):
        existing = []

    points = list(existing)
    for field in PAYOFF_MERGE_FIELDS:
        value = flat.get(field)
        if _has_content(value):
            formatted = _format_value(value).strip()
            if formatted and formatted not in points:
                points.append(formatted)
    return points


def _build_required_beats(flat: dict) -> list[str]:
    """Build required_beats by collecting beat-related field values."""
    existing = flat.get("required_beats", [])
    if isinstance(existing, str):
        try:
            existing = json.loads(existing)
        except (json.JSONDecodeError, TypeError):
            existing = [existing] if existing else []
    if not isinstance(existing, list):
        existing = []

    beats = list(existing)
    for field in BEATS_MERGE_FIELDS:
        value = flat.get(field)
        if _has_content(value):
            formatted = _format_value(value).strip()
            if formatted and formatted not in beats:
                beats.append(formatted)
    return beats


def _build_conflict(flat: dict) -> str:
    """Build conflict field by merging conflict_actions into existing conflict."""
    existing = str(flat.get("conflict") or "").strip()
    parts = [existing] if existing else []
    for field in CONFLICT_MERGE_FIELDS:
        value = flat.get(field)
        if _has_content(value):
            formatted = _format_value(value).strip()
            if formatted:
                parts.append(formatted)
    return "; ".join(p for p in parts if p)


def _has_content(value) -> bool:
    """Check if a field has meaningful content."""
    if value is None or value == "":
        return False
    if isinstance(value, (list, dict)):
        return len(value) > 0
    if isinstance(value, bool):
        return value  # True is meaningful for bool fields
    if isinstance(value, (int, float)):
        return value != 0
    return bool(str(value).strip())


def _format_value(value) -> str:
    """Format a field value for notes inclusion."""
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def migrate_brief(brief_data: dict) -> dict:
    """Migrate a single brief_data dict. Returns updated dict."""
    flat = _flatten_brief(brief_data)

    # Preserve tier1/tier2 structure if input was nested
    is_nested = "tier1" in brief_data or "tier2" in brief_data

    # Build new fields
    notes_val = _build_notes_section(flat)
    payoff_val = _build_payoff_points(flat)
    conflict_val = _build_conflict(flat)
    beats_val = _build_required_beats(flat)

    if is_nested:
        if "tier1" not in brief_data:
            brief_data["tier1"] = {}
        if "tier2" not in brief_data:
            brief_data["tier2"] = {}
        # Update new fields in flat positions (both tier1 and tier2 accessible)
        # For nested shape, notes/conflict go to tier2
        brief_data["tier2"]["notes"] = notes_val
        brief_data["tier2"]["payoff_points"] = json.dumps(payoff_val, ensure_ascii=False)
        brief_data["tier2"]["conflict"] = conflict_val
        brief_data["tier2"]["required_beats"] = json.dumps(beats_val, ensure_ascii=False)
    else:
        brief_data["notes"] = notes_val
        brief_data["payoff_points"] = payoff_val
        brief_data["conflict"] = conflict_val
        brief_data["required_beats"] = beats_val

    # Also add new fields to flat (needed by schemas.ChapterBrief)
    if "notes" not in brief_data and "tier1" not in brief_data:
        brief_data["notes"] = notes_val
    if "conflict" not in brief_data and "tier1" not in brief_data:
        brief_data["conflict"] = conflict_val

    return brief_data


# ── Main runner ───────────────────────────────────────────────────────

def run_migration(db_path: str, dry_run: bool = False) -> MigrationReport:
    """Execute field migration on chapter_briefs table.

    Args:
        db_path: Path to SQLite database.
        dry_run: If True, preview changes without writing.

    Returns:
        MigrationReport with counts and details.
    """
    report = MigrationReport()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Count total
        total_row = conn.execute("SELECT COUNT(*) FROM chapter_briefs").fetchone()
        report.total = total_row[0] if total_row else 0

        # Create backup table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS _chapter_briefs_migration_backup (
                id INTEGER PRIMARY KEY,
                project_id TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                brief_data TEXT NOT NULL,
                workflow_run_id TEXT,
                created_at TEXT,
                backed_up_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # Backup all rows
        conn.execute("""
            INSERT OR IGNORE INTO _chapter_briefs_migration_backup
                (id, project_id, chapter_number, brief_data, workflow_run_id, created_at)
            SELECT id, project_id, chapter_number, brief_data, workflow_run_id, created_at
            FROM chapter_briefs
        """)
        backup_count = conn.total_changes
        report.details.append(f"Backed up {backup_count} rows to _chapter_briefs_migration_backup")

        if dry_run:
            report.details.append("DRY RUN - no data written to chapter_briefs")

        # Process each row
        rows = conn.execute("SELECT * FROM chapter_briefs").fetchall()
        for row in rows:
            row_dict = dict(row)
            try:
                brief_data = json.loads(row_dict["brief_data"])
            except (json.JSONDecodeError, TypeError):
                report.skipped += 1
                report.details.append(
                    f"SKIP {row_dict['project_id']}/ch{row_dict['chapter_number']}: "
                    f"invalid JSON"
                )
                continue

            migrated = migrate_brief(brief_data)
            new_json = json.dumps(migrated, ensure_ascii=False)

            if new_json == row_dict["brief_data"]:
                report.skipped += 1
                continue

            report.migrated += 1
            project = row_dict["project_id"]
            ch = row_dict["chapter_number"]
            report.details.append(f"MIGRATED {project}/ch{ch}")

            if not dry_run:
                conn.execute(
                    "UPDATE chapter_briefs SET brief_data=? WHERE id=?",
                    (new_json, row_dict["id"]),
                )

        if not dry_run:
            conn.commit()
            report.details.append(f"Committed {report.migrated} migrations")
        else:
            conn.rollback()

    finally:
        conn.close()

    return report


# ── CLI ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    db_path = None
    for i, arg in enumerate(sys.argv):
        if arg == "--db-path" and i + 1 < len(sys.argv):
            db_path = sys.argv[i + 1]
            break

    if not db_path:
        print("Usage: python -m novel_factory.db.data_migrations.001_... --db-path <db> [--dry-run]")
        sys.exit(1)

    if not Path(db_path).exists():
        print(f"DB not found: {db_path}")
        sys.exit(1)

    print(f"{'[DRY RUN] ' if dry_run else ''}Migrating {db_path}...")
    report = run_migration(db_path, dry_run=dry_run)

    print(f"\nTotal: {report.total}")
    print(f"Migrated: {report.migrated}")
    print(f"Skipped: {report.skipped}")
    if report.details:
        for d in report.details[:20]:
            print(f"  {d}")
        if len(report.details) > 20:
            print(f"  ... ({len(report.details) - 20} more)")
