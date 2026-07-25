UNIT_ALIASES = {
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "g": "gms",
    "gm": "gms",
    "gms": "gms",
    "gram": "gms",
    "grams": "gms",
    "kg/gms": "gms",
    "l": "lt",
    "lt": "lt",
    "ltr": "lt",
    "litre": "lt",
    "litres": "lt",
    "liter": "lt",
    "liters": "lt",
    "ml": "ml",
    "mls": "ml",
    "millilitre": "ml",
    "milliliter": "ml",
    "lt/ml": "ml",
    "pc": "pcs",
    "pcs": "pcs",
    "piece": "pcs",
    "pieces": "pcs",
    "item": "pcs",
    "items": "pcs",
    "pkt": "pkt",
    "pkts": "pkt",
    "packet": "pkt",
    "packets": "pkt",
    "tray": "tray",
    "trays": "tray",
}


# Multiplier to convert from canonical unit to its group's base unit.
# Weight -> gms, Volume -> ml, Count -> pcs/pkt.
UNIT_TO_BASE = {
    "kg": ("gms", 1000.0),
    "gms": ("gms", 1.0),
    "lt": ("ml", 1000.0),
    "ml": ("ml", 1.0),
    "pcs": ("pcs", 1.0),
    "pkt": ("pkt", 1.0),
    "tray": ("pcs", 30.0),
}


def canonical_unit(unit: str | None) -> str:
    raw = str(unit or "").strip().lower()
    return UNIT_ALIASES.get(raw, raw)


def is_supported_unit(unit: str | None) -> bool:
    return canonical_unit(unit) in UNIT_TO_BASE


def convert_to_base(quantity: float, unit: str | None) -> tuple[float | None, str | None]:
    canonical = canonical_unit(unit)
    conversion = UNIT_TO_BASE.get(canonical)
    if not conversion:
        return None, None

    base_unit, factor = conversion
    return float(quantity) * factor, base_unit


def normalize_units(units: list[str] | None) -> list[str]:
    if not isinstance(units, list):
        return []

    cleaned = []
    for raw in units:
        unit = canonical_unit(raw)
        if unit and unit not in cleaned and unit in UNIT_TO_BASE:
            cleaned.append(unit)
    return cleaned


def units_share_base(units: list[str]) -> tuple[bool, str | None]:
    base_unit = None
    for unit in units:
        _, base = convert_to_base(1, unit)
        if not base:
            return False, None
        if base_unit and base_unit != base:
            return False, None
        base_unit = base
    return True, base_unit
