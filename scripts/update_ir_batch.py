#!/usr/bin/env python3
"""
Update IR batch result JSON files with web-searched IR page URLs.

Usage:
    python3 scripts/update_ir_batch.py <batch_id> <code> <ir_url> <method> <notes>

Or pipe in TSV data:
    echo "code|ir_url|method|notes" | python3 scripts/update_ir_batch.py --batch 004 --batch 005 --pipe
"""

import json
import sys
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "ir_batches")


def load_batch(batch_id: str) -> list:
    """Load a batch JSON file."""
    fname = f"result_{batch_id}.json"
    path = os.path.join(DATA_DIR, fname)
    with open(path) as f:
        return json.load(f)


def save_batch(batch_id: str, data: list):
    """Save a batch JSON file."""
    fname = f"result_{batch_id}.json"
    path = os.path.join(DATA_DIR, fname)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_entry(data: list, code: str, ir_url: str, method: str, notes: str) -> bool:
    """Update a single entry in the data list. Returns True if found."""
    for item in data:
        if item["code"] == code:
            if ir_url and ir_url != "NOT_FOUND":
                item["ir_url"] = ir_url
            item["method"] = method
            item["notes"] = notes
            return True
    return False


def main():
    if "--pipe" in sys.argv:
        # Pipe mode: read lines from stdin
        # Format: code|ir_url|method|notes
        # Or: code|name|ir_url|method|notes (name is ignored)
        batch_ids = []
        for i, arg in enumerate(sys.argv):
            if arg == "--batch" and i + 1 < len(sys.argv):
                batch_ids.append(sys.argv[i + 1])

        if not batch_ids:
            batch_ids = ["004", "005"]

        # Load both batches
        batches = {}
        for bid in batch_ids:
            batches[bid] = load_batch(bid)

        updated = 0
        not_found = 0

        for line in sys.stdin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("|")
            if len(parts) == 5:
                # code|name|ir_url|method|notes
                code, name, ir_url, method, notes = parts
            elif len(parts) == 4:
                code, ir_url, method, notes = parts
            else:
                print(f"SKIP (bad format): {line}", file=sys.stderr)
                continue

            found = False
            for bid, data in batches.items():
                if update_entry(data, code, ir_url, method, notes):
                    found = True
                    updated += 1
                    break

            if not found:
                not_found += 1
                print(f"WARN: code {code} not found in any batch", file=sys.stderr)

        # Save
        for bid, data in batches.items():
            save_batch(bid, data)
            print(f"Saved result_{bid}.json ({len(data)} entries)")

        print(f"\nUpdated: {updated}, Not found: {not_found}")

    else:
        # Single-entry mode
        if len(sys.argv) < 4:
            print("Usage: python3 update_ir_batch.py <batch_id> <code> <ir_url> <method> <notes>")
            sys.exit(1)

        batch_id = sys.argv[1]
        code = sys.argv[2]
        ir_url = sys.argv[3]
        method = sys.argv[4] if len(sys.argv) > 4 else "web_search"
        notes = sys.argv[5] if len(sys.argv) > 5 else ""

        data = load_batch(batch_id)
        if update_entry(data, code, ir_url, method, notes):
            save_batch(batch_id, data)
            print(f"Updated {code} in result_{batch_id}.json")
        else:
            print(f"ERROR: {code} not found in result_{batch_id}.json")
            sys.exit(1)


if __name__ == "__main__":
    main()
