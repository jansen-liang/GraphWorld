"""Procedural scene generation helpers.

The generation package depends on canonical contracts from ``backend.core``;
the runtime does not depend on this package.
"""

__all__ = ["Ontology", "load_ontology", "DOMAIN_PROFILES", "generate_scene"]


def __getattr__(name: str):
    # Lazy exports avoid the ontology <-> core.assets import cycle during
    # object-template initialization.
    if name in {"Ontology", "load_ontology"}:
        from .ontology import Ontology, load_ontology
        return {"Ontology": Ontology, "load_ontology": load_ontology}[name]
    if name in {"DOMAIN_PROFILES", "generate_scene"}:
        from .symbolic_scene_generator import DOMAIN_PROFILES, generate_scene
        return {"DOMAIN_PROFILES": DOMAIN_PROFILES, "generate_scene": generate_scene}[name]
    raise AttributeError(name)
