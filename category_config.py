"""Catálogo e seleção persistente dos subtipos do mercado do Albion."""

from __future__ import annotations

from typing import Any


ITEM_TIERS: tuple[int, ...] = tuple(range(2, 9))
DEFAULT_TIER_ENABLED: dict[int, bool] = {
    tier: tier >= 4 for tier in ITEM_TIERS
}


CATEGORY_SUBTYPES: dict[str, tuple[str, ...]] = {
    "ARMAS": (
        "Arco",
        "Besta",
        "Machado",
        "Adaga",
        "Martelo",
        "Luvas de Guerra",
        "Maça",
        "Bordão",
        "Lança",
        "Espada",
        "Cajado Arcano",
        "Cajado Amaldiçoado",
        "Cajado de Fogo",
        "Cajado de Gelo",
        "Cajado Sagrado",
        "Cajado da Natureza",
        "Cajado Metamorfo",
    ),
    "PEITORAL": (
        "Robes de Tecido",
        "Casacos de Couro",
        "Armadura de Placa",
    ),
    "CAPACETES": (
        "Capote de Tecido",
        "Capuz de Couro",
        "Elmo de Placa",
    ),
    "BOTAS": (
        "Sandálias de Tecido",
        "Sapatos de Couro",
        "Botas de Placa",
        "Outros",
    ),
    # Mantém o mesmo identificador usado pela interface e pelos offsets.
    "MÃO SECUNDARIA": (
        "Mago",
        "Caçador",
        "Guerreiro",
    ),
    "CAPAS": (
        "Capa",
        "Bridgewatch",
        "Fort Sterling",
        "Lymhurst",
        "Martlock",
        "Thetford",
        "Caerleon",
        "Brecilien",
        "Hereges",
        "Mortos-vivos",
        "Protetores",
        "Morgana",
        "Avaloniano",
        "Demônio",
        "Contrabandista",
    ),
    "BOLSAS": (
        "Bolsas",
        "Sacola da Visão",
    ),
    "EQUIP COLETA": (
        "Peixe",
        "Fibra",
        "Pelego",
        "Minério",
        "Pedra",
        "Madeira",
        "Rastreamento",
    ),
}


def merge_subtype_settings(raw: Any) -> dict[str, dict[str, bool]]:
    """Combina configurações antigas com o catálogo atual sem perder escolhas."""
    source = raw if isinstance(raw, dict) else {}
    merged: dict[str, dict[str, bool]] = {}
    for category, subtypes in CATEGORY_SUBTYPES.items():
        saved = source.get(category)
        saved = saved if isinstance(saved, dict) else {}
        merged[category] = {
            subtype: bool(saved.get(subtype, True)) for subtype in subtypes
        }
    return merged


def merge_tier_settings(raw: Any) -> dict[str, dict[str, dict[int, bool]]]:
    """Carrega tiers por subtipo; arquivos antigos mantêm todos habilitados."""
    source = raw if isinstance(raw, dict) else {}
    merged: dict[str, dict[str, dict[int, bool]]] = {}
    for category, subtypes in CATEGORY_SUBTYPES.items():
        saved_category = source.get(category)
        saved_category = saved_category if isinstance(saved_category, dict) else {}
        merged[category] = {}
        for subtype in subtypes:
            saved_subtype = saved_category.get(subtype)
            saved_subtype = saved_subtype if isinstance(saved_subtype, dict) else {}
            merged[category][subtype] = {
                tier: bool(
                    saved_subtype.get(
                        str(tier),
                        saved_subtype.get(tier, DEFAULT_TIER_ENABLED[tier]),
                    )
                )
                for tier in ITEM_TIERS
            }
    return merged


def build_navigation_targets(
    sequence: Any,
    category_enabled: Any,
    subtype_enabled: Any,
    category_keys: dict[str, str],
    tier_enabled: Any = None,
) -> list[dict[str, Any]]:
    """Expande a ordem das categorias nos subtipos marcados pela interface."""
    ordered = [name for name in sequence or () if name in category_keys]
    ordered.extend(name for name in category_keys if name not in ordered)
    enabled = category_enabled if isinstance(category_enabled, dict) else {}
    subtype_settings = merge_subtype_settings(subtype_enabled)
    tier_settings = merge_tier_settings(tier_enabled)

    targets: list[dict[str, Any]] = []
    for category in ordered:
        if not bool(enabled.get(category, True)):
            continue
        available = CATEGORY_SUBTYPES.get(category, ())
        selected = [
            subtype
            for subtype in available
            if subtype_settings[category].get(subtype, True)
        ]
        for subtype in selected:
            allowed_tiers = [
                tier
                for tier in ITEM_TIERS
                if tier_settings[category][subtype].get(tier, True)
            ]
            if not allowed_tiers:
                continue
            targets.append(
                {
                    "category": category,
                    "key": category_keys[category],
                    "subtype": subtype,
                    "label": f"{category} > {subtype}",
                    "tiers": allowed_tiers,
                }
            )
    return targets
