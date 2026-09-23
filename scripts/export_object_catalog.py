#!/usr/bin/env python3
"""Export the complete Web object catalog as a repository asset."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.db.models import ObjectCatalog
from backend.app.db.session import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT_DIR / "backend/data/object_catalog/object_catalog.json",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        entries = list(db.scalars(select(ObjectCatalog).order_by(ObjectCatalog.semantic_type)).all())

    payload = {
        "schema_version": 1,
        "object_count": len(entries),
        "objects": [
            {
                "semantic_type": entry.semantic_type,
                "name": entry.name,
                "name_cn": entry.name_cn,
                "category": entry.category,
                "dimensions_cm": {
                    "width": entry.width_cm,
                    "depth": entry.depth_cm,
                    "height": entry.height_cm,
                },
                "capabilities": entry.capabilities,
                "state_schema": entry.state_schema,
                "default_states": entry.default_states,
                "is_active": entry.is_active,
            }
            for entry in entries
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
