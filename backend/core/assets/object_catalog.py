"""Resolution of external object labels into the canonical object catalog.

This is a migration/catalog layer. It does not turn every dataset label into
a runtime template: labels with no current causal semantics remain candidates
or deferred entries with their external prior preserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .object_library import OBJECT_LIBRARY, OBJECT_TYPE_ALIASES
from .object_registry import DEFERRED_OBJECTS


class CatalogDisposition(str, Enum):
    ALIAS = "alias"
    TEMPLATE = "template"
    DEFERRED = "deferred"
    CANDIDATE = "new_template_candidate"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class CatalogResolution:
    raw_label: str
    disposition: CatalogDisposition
    canonical_type: str | None = None
    reason: str = ""


# High-confidence semantic merges. These are not new runtime templates.
EXTERNAL_ALIASES: dict[str, str] = {
    "handtowelholder": "towel_holder",
    "towelholder": "towel_holder",
    "handtowel": "towel",
}
OBJECT_TYPE_ALIASES.update(EXTERNAL_ALIASES)


# Objects that can be represented with the current nine actions and state
# vocabulary, but still need a deliberate template declaration and placement
# policy. Keeping this list explicit prevents accidental fallback templates.
TEMPLATE_CANDIDATES = frozenset({
    "statue", "keychain", "cellphone", "bread", "egg", "fork", "peppershaker",
    "saltshaker", "plunger", "scrubbrush", "soapbar", "spatula", "spoon", "towel",
    "dresser", "tissuebox", "watch", "newspaper", "bathtub", "bathtubbasin",
    "curtains", "kettle", "showerdoor", "baseballbat", "papertowelroll", "tvstand",
    "showercurtain", "ladle", "showerglass", "basketball", "safe",
    "teddybear", "tennisracket", "winebottle", "laundryhamper", "poster", "roomdecor",
    "bottle", "garbagebag", "dumbbell", "dogbed", "footstool", "ottoman", "aluminumfoil",
    "tabletopdecor", "vacuumcleaner", "clothesdryer", "doorframe", "doorway", "toaster",
})


UNSUPPORTED = frozenset({"doorframe", "doorway"})


def resolve_catalog_label(raw_label: str) -> CatalogResolution:
    raw = str(raw_label or "").strip().lower().replace(" ", "_")
    if raw in EXTERNAL_ALIASES:
        return CatalogResolution(raw, CatalogDisposition.ALIAS, EXTERNAL_ALIASES[raw], "same holder/towel semantics")
    if raw in OBJECT_LIBRARY:
        return CatalogResolution(raw, CatalogDisposition.TEMPLATE, raw, "already present in canonical library")
    if raw in DEFERRED_OBJECTS:
        return CatalogResolution(raw, CatalogDisposition.DEFERRED, None, DEFERRED_OBJECTS[raw].reason)
    if raw in UNSUPPORTED:
        return CatalogResolution(raw, CatalogDisposition.UNSUPPORTED, None, "structural asset label, not an interactive object")
    if raw in TEMPLATE_CANDIDATES:
        return CatalogResolution(raw, CatalogDisposition.CANDIDATE, None, "needs explicit states, capabilities, and placement policy")
    return CatalogResolution(raw, CatalogDisposition.CANDIDATE, None, "not yet assigned a canonical runtime meaning")


def resolve_catalog_labels(labels: list[str] | tuple[str, ...]) -> list[CatalogResolution]:
    return [resolve_catalog_label(label) for label in sorted(set(labels))]


__all__ = [
    "CatalogDisposition",
    "CatalogResolution",
    "EXTERNAL_ALIASES",
    "TEMPLATE_CANDIDATES",
    "resolve_catalog_label",
    "resolve_catalog_labels",
]
