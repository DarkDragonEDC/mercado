"""Perfis de configuração que alimentam os limites financeiros existentes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


PROFILE_CONSERVATIVE = "conservador"
PROFILE_BALANCED = "equilibrado"
PROFILE_AGGRESSIVE = "agressivo"
PROFILE_CUSTOM = "personalizado"

PROFILE_LABELS = {
    PROFILE_CONSERVATIVE: "Conservador",
    PROFILE_BALANCED: "Equilibrado",
    PROFILE_AGGRESSIVE: "Agressivo",
    PROFILE_CUSTOM: "Personalizado",
}

# lucro mínimo por venda, exposição da banca em pontos-base
PROFILE_RULES: dict[str, tuple[float, int]] = {
    PROFILE_CONSERVATIVE: (50.0, 50),   # 0,5%
    PROFILE_BALANCED: (40.0, 100),      # 1%
    PROFILE_AGGRESSIVE: (30.0, 200),    # 2%
}

FINANCIAL_RULE_VERSION = 2


@dataclass(frozen=True)
class EffectivePurchaseSettings:
    profile: str
    operational_bank: int
    minimum_profit_percent: float
    order_limit: int
    exposure_basis_points: int | None

    @property
    def exposure_percent(self) -> float | None:
        if self.exposure_basis_points is None:
            return None
        return self.exposure_basis_points / 100

    @property
    def max_percent(self) -> float:
        """Alias temporário para integrações anteriores à regra financeira v2."""
        return self.minimum_profit_percent


def normalize_profile(value: Any) -> str:
    profile = str(value or "").strip().lower()
    return profile if profile in PROFILE_LABELS else PROFILE_CUSTOM


def parse_silver(value: Any) -> int:
    """Converte prata inteira aceitando ``50.000.000`` e ``50000000``."""
    if isinstance(value, bool):
        raise ValueError("Valor monetário inválido.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value or "").strip().replace(" ", "")
    if not text:
        raise ValueError("Informe um valor em prata.")
    if re.fullmatch(r"[+-]?\d{1,3}(?:[.,]\d{3})+", text):
        return int(text.replace(".", "").replace(",", ""))
    normalized = text.replace(",", ".")
    try:
        return int(float(normalized))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Informe um valor inteiro válido em prata.") from exc


def format_silver(value: int) -> str:
    return f"{int(value):,}".replace(",", ".")


def resolve_purchase_profile(
    profile: Any,
    operational_bank: Any,
    custom_percent: Any | None = None,
    custom_order_limit: Any | None = None,
) -> EffectivePurchaseSettings:
    """Resolve a UX de perfil nos mesmos ``lucro`` e ``valor_max`` legados."""
    normalized_profile = normalize_profile(profile)
    bank = parse_silver(operational_bank)
    if bank < 0:
        raise ValueError("A banca operacional não pode ser negativa.")

    if normalized_profile == PROFILE_CUSTOM:
        try:
            minimum_profit_percent = float(custom_percent)
        except (TypeError, ValueError) as exc:
            raise ValueError("Informe um percentual personalizado válido.") from exc
        order_limit = parse_silver(custom_order_limit)
        if not 0 <= minimum_profit_percent <= 100:
            raise ValueError("O percentual deve ficar entre 0 e 100%.")
        if order_limit <= 0:
            raise ValueError("O limite por ordem deve ser maior que zero.")
        return EffectivePurchaseSettings(
            normalized_profile,
            bank,
            minimum_profit_percent,
            order_limit,
            None,
        )

    if bank <= 0:
        raise ValueError("Informe uma banca maior que zero para usar um perfil automático.")
    minimum_profit_percent, exposure_basis_points = PROFILE_RULES[normalized_profile]
    # Pontos-base mantêm o cálculo inteiro e sempre arredondam para baixo.
    order_limit = bank * exposure_basis_points // 10_000
    if order_limit <= 0:
        raise ValueError("A banca informada gera um limite por ordem igual a zero.")
    return EffectivePurchaseSettings(
        normalized_profile,
        bank,
        minimum_profit_percent,
        order_limit,
        exposure_basis_points,
    )


def settings_from_legacy_config(data: Any) -> EffectivePurchaseSettings:
    """Migra custo máximo antigo para margem mínima sem mudar o limite efetivo."""
    source = data if isinstance(data, dict) else {}
    is_v2 = int(source.get("financial_rule_version", 0) or 0) >= FINANCIAL_RULE_VERSION
    if not source:
        configured_percent = 40.0
    elif is_v2 or "lucro_minimo_venda" in source:
        configured_percent = source.get("lucro_minimo_venda", 40.0)
    else:
        try:
            configured_percent = 100.0 - float(source.get("lucro", 80.0))
        except (TypeError, ValueError):
            configured_percent = 40.0
    if "perfil_compra" not in source:
        return resolve_purchase_profile(
            PROFILE_CUSTOM,
            source.get("banca_operacional", 0),
            configured_percent,
            source.get("valor_max", 1_000_000),
        )

    if not is_v2:
        return resolve_purchase_profile(
            PROFILE_CUSTOM,
            source.get("banca_operacional", 0),
            configured_percent,
            source.get("valor_max", 1_000_000),
        )

    profile = normalize_profile(source.get("perfil_compra"))
    bank = source.get("banca_operacional", 0)
    try:
        return resolve_purchase_profile(
            profile,
            bank,
            configured_percent,
            source.get("valor_max", 1_000_000),
        )
    except ValueError:
        # Um preset corrompido não deve apagar os limites efetivos anteriores.
        try:
            fallback_bank = max(0, parse_silver(bank))
        except ValueError:
            fallback_bank = 0
        return resolve_purchase_profile(
            PROFILE_CUSTOM,
            fallback_bank,
            configured_percent,
            source.get("valor_max", 1_000_000),
        )
