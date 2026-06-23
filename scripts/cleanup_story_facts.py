#!/usr/bin/env python3
"""Cleanup script for duplicate active story_facts.

v6.10.12: One-off deduplication tool. For a given project, scans all active
story_facts and marks older duplicates (same subject+attribute, lower
source_chapter) as status='superseded', keeping only the latest per key.

Usage:
    python scripts/cleanup_story_facts.py <db_path> <project_id>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from repo root without package install
sys.path.insert(0, str(Path(__file__).parent.parent))

from novel_factory.db.repository import Repository


def cleanup_project(repo: Repository, project_id: str, dry_run: bool = True) -> dict:
    """Mark older duplicate active facts as superseded."""
    facts = repo.list_story_facts(project_id, status="active")
    if not facts:
        return {"project_id": project_id, "total_active": 0, "superseded": 0, "kept": 0}

    # Group by subject.attribute
    grouped: dict[str, list[dict]] = {}
    for fact in facts:
        subject = str(fact.get("subject") or "").strip()
        attribute = str(fact.get("attribute") or "").strip()
        key = f"{subject}.{attribute}" if subject and attribute else (subject or attribute or fact.get("fact_key", ""))
        grouped.setdefault(key, []).append(fact)

    superseded_count = 0
    kept_count = 0

    for key, group in grouped.items():
        if len(group) <= 1:
            kept_count += 1
            continue
        # Keep the one with highest source_chapter
        latest = max(
            group,
            key=lambda f: int(f.get("source_chapter") or f.get("last_changed_chapter") or 0),
        )
        for fact in group:
            if fact["id"] == latest["id"]:
                continue
            if not dry_run:
                try:
                    repo.update_story_fact(fact["id"], {"status": "superseded"})
                except Exception as e:
                    print(f"  Warning: failed to supersede {fact['id']}: {e}")
                    continue
            superseded_count += 1
        kept_count += 1

    return {
        "project_id": project_id,
        "total_active": len(facts),
        "superseded": superseded_count,
        "kept": kept_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup duplicate active story_facts")
    parser.add_argument("db_path", help="Path to SQLite database")
    parser.add_argument("project_id", help="Project ID to clean up")
    parser.add_argument("--execute", action="store_true", help="Actually modify the database (default is dry-run)")
    args = parser.parse_args()

    repo = Repository(args.db_path)
    result = cleanup_project(repo, args.project_id, dry_run=not args.execute)

    print(f"Project: {result['project_id']}")
    print(f"Total active facts: {result['total_active']}")
    print(f"Facts to supersede: {result['superseded']}")
    print(f"Keys to keep:       {result['kept']}")

    if not args.execute:
        print("\nThis was a dry-run. Pass --execute to apply changes.")
        sys.exit(0)

    print("\nChanges applied.")


if __name__ == "__main__":
    main()
