"""Versioned domain knowledge loader for procedural generation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DOMAINS = ("home", "office", "hospital", "supermarket", "factory")
COMMON_FILES = ("world", "connectivity", "placement", "resources", "environment", "validation")
DOMAIN_FILES = ("domain", "rooms", "topology", "objects", "tasks", "npc_events")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_domain_knowledge(domain: str) -> dict[str, Any]:
    key = str(domain).strip().lower()
    if key not in DOMAINS:
        raise KeyError(f"Unknown domain: {domain}")
    return {
        "manifest": _read(ROOT / "manifest.json"),
        "common_rules": {name: _read(ROOT / "common_rules" / f"{name}.json") for name in COMMON_FILES},
        "domain_rules": {name: _read(ROOT / "domain_rules" / key / f"{name}.json") for name in DOMAIN_FILES},
    }


__all__ = ["COMMON_FILES", "DOMAIN_FILES", "DOMAINS", "load_domain_knowledge"]
