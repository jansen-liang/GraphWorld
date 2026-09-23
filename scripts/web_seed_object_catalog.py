#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.db.models import ObjectCatalog
from backend.app.db.session import SessionLocal
from backend.app.runtime.scene_layout import OBJECT_DIMENSIONS_CM, _object_dimensions_cm
from backend.core.assets.object_library import OBJECT_LIBRARY


# Catalog-level physical priors. These are object footprints, not grid cells.
# Keeping them here makes the seed auditable and prevents generic 10x10x80cm
# fallback geometry from leaking into the editor.
PHYSICAL_DIMENSIONS_CM: dict[str, tuple[int, int, int]] = {
    "air_conditioner": (90, 25, 30), "aluminumfoil": (25, 8, 8), "baseballbat": (8, 8, 85), "basketball": (24, 24, 24),
    "bathtub": (170, 75, 60), "bathtubbasin": (50, 35, 20), "book": (15, 22, 3), "bottle": (7, 7, 25), "bowl": (22, 22, 10), "box": (35, 25, 20),
    "bread": (25, 12, 10), "cart": (90, 55, 95), "cellphone": (8, 16, 1), "cleaningcloth": (30, 30, 1), "clothes": (45, 35, 5),
    "clothesdryer": (60, 65, 85), "coffee": (8, 8, 12), "coffee_beans": (10, 10, 8), "coffee_table": (110, 60, 45), "computer": (55, 20, 45),
    "cup": (9, 9, 11), "dispenser": (30, 30, 45), "doctor_coat": (55, 35, 8), "drink": (7, 7, 22), "dresser": (100, 45, 85),
    "drying_rack": (120, 45, 150), "dumbbell": (12, 12, 28), "egg": (5, 5, 7), "footstool": (45, 35, 30), "fork": (3, 3, 20),
    "garbagebag": (35, 20, 45), "hand_sanitizer_dispenser": (12, 10, 25), "ink_cartridge": (12, 5, 8), "juice": (7, 7, 22), "keychain": (4, 2, 1),
    "ladle": (8, 8, 35), "laundryhamper": (45, 45, 60), "locker": (50, 50, 180), "machine": (80, 70, 100), "medical_cart": (70, 50, 100),
    "medical_form": (21, 30, 0.2), "medicine_box": (18, 12, 8), "medicine_fridge": (70, 70, 180), "milk": (7, 7, 22), "mirror": (80, 4, 100),
    "mug": (10, 10, 11), "newspaper": (30, 42, 1), "nurse_uniform": (55, 35, 8), "ottoman": (60, 60, 40), "painting": (100, 5, 70),
    "paper_pack": (22, 30, 5), "pepper_refill": (8, 8, 12), "peppershaker": (6, 6, 12), "plant": (30, 30, 60), "plate": (24, 24, 3),
    "plunger": (15, 15, 55), "poster": (60, 2, 90), "prescription_sheet": (21, 30, 0.2), "printer": (45, 40, 30), "receipt": (8, 20, 0.2),
    "refrigerated_medicine": (8, 8, 5), "remote": (5, 18, 2), "roomdecor": (30, 10, 30), "salt_refill": (8, 8, 12), "saltshaker": (6, 6, 12),
    "scrubbrush": (8, 8, 25), "shoes": (30, 12, 10), "shower": (25, 25, 220), "signboard": (80, 5, 40), "sink": (70, 50, 25),
    "soap_refill": (10, 10, 18), "soapbar": (8, 6, 3), "soapbottle": (8, 8, 22), "spoon": (4, 4, 20), "spraybottle": (9, 9, 25),
    "stationery": (15, 10, 4), "statue": (30, 30, 45), "stove": (70, 60, 90), "syringe": (2, 2, 15), "tabletopdecor": (20, 20, 20),
    "teddybear": (25, 20, 30), "television": (110, 8, 70), "tennisracket": (25, 3, 70), "tissue_refill": (20, 10, 5), "toilet": (70, 70, 75),
    "toilet_brush": (12, 12, 40), "toothpaste_refill": (5, 5, 18), "towel": (60, 30, 2), "towel_holder": (50, 10, 10), "trash_bin": (35, 35, 50),
    "tvstand": (120, 40, 55), "vacuumcleaner": (35, 35, 110), "vase": (15, 15, 25), "water_dispenser": (35, 35, 110), "water_refill": (10, 10, 20),
    "wheelchair": (65, 100, 110), "winebottle": (8, 8, 30),
    "display": (100, 10, 60), "dogbed": (80, 60, 20), "door": (90, 10, 210), "pillow": (60, 40, 15), "watch": (4, 4, 1),
}


def seed() -> int:
    changed = 0
    with SessionLocal() as db:
        for semantic_type, template in OBJECT_LIBRARY.items():
            dimensions = PHYSICAL_DIMENSIONS_CM.get(semantic_type) or OBJECT_DIMENSIONS_CM.get(semantic_type)
            if dimensions is None:
                dimensions = _object_dimensions_cm({"semantic_type": semantic_type}, {"width_cells": 1, "depth_cells": 1})
            entry = db.get(ObjectCatalog, semantic_type)
            payload = {
                "name": template.name,
                "name_cn": template.name_cn,
                "category": template.family.value,
                "width_cm": dimensions[0],
                "depth_cm": dimensions[1],
                "height_cm": dimensions[2],
                "capabilities": [capability.name for capability in template.capabilities],
                "state_schema": template.state_schema,
                "default_states": template.default_states,
                "is_active": True,
            }
            if entry is None:
                db.add(ObjectCatalog(semantic_type=semantic_type, **payload))
            else:
                for key, value in payload.items():
                    setattr(entry, key, value)
            changed += 1
        db.commit()
    return changed


if __name__ == "__main__":
    print(f"seeded {seed()} object catalog entries")
