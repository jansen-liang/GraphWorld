"""Finite-resource refill compatibility and state transitions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .predicates import node, semantic


@dataclass(frozen=True)
class RefillRule:
    target_semantic: str
    supply_semantic: str
    state_key: str


REFILL_RULES: tuple[RefillRule, ...] = (
    RefillRule("tissuebox", "tissue_refill", "count"),
    RefillRule("soapbottle", "soap_refill", "amount"),
    RefillRule("spraybottle", "water_refill", "uses_left"),
    RefillRule("peppershaker", "pepper_refill", "uses_left"),
    RefillRule("saltshaker", "salt_refill", "uses_left"),
    RefillRule("toothpaste", "toothpaste_refill", "uses_left"),
    RefillRule("printer", "paper_pack", "count"),
    RefillRule("printer", "ink_cartridge", "amount"),
)


def refill_rule(state: dict[str, Any], target_id: str, supply_id: str) -> RefillRule | None:
    target_semantic = semantic(node(state, target_id))
    supply_semantic = semantic(node(state, supply_id))
    return next(
        (rule for rule in REFILL_RULES if rule.target_semantic == target_semantic and rule.supply_semantic == supply_semantic),
        None,
    )


__all__ = ["REFILL_RULES", "RefillRule", "refill_rule"]
