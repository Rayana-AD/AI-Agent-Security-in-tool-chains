"""Tool sensitivity tiers for graduated carry (not benchmark-specific)."""

from __future__ import annotations

import json
import re
from contextvars import ContextVar
from typing import Any

from bio_harness.provenance.constants import SENSITIVE_TOOLS

# Exfil / funds / messaging = high; scoped share / booking = mid; read = low.
TOOL_SENSITIVITY: dict[str, float] = {
    "send_email": 1.0,
    "send_money": 1.0,
    "transfer_money": 1.0,
    "update_scheduled_transaction": 0.9,
    "delete_file": 0.85,
    "share_file": 0.75,
    "send_channel_message": 0.8,
    "send_direct_message": 0.8,
    "post_webpage": 0.7,
    "invite_user_to_slack": 0.65,
    "remove_user_from_slack": 0.65,
    "add_user_to_channel": 0.65,
    "reserve_hotel": 0.5,
}

# Max tool sensitivity allowed uphill at each carry level (finer than boolean sensitive).
CARRY_SENS_CEILING: dict[int, float] = {
    0: 1.0,
    1: 0.85,  # WATCH: block exfil tier, allow mid-tier share/reserve
    2: 0.70,  # ELEVATED
    3: 0.0,   # LOCKDOWN
}

_ceiling_table_override: ContextVar[dict[int, float] | None] = ContextVar(
    "bio_harness_carry_ceiling_table", default=None
)
_ceiling_enabled: ContextVar[bool] = ContextVar(
    "bio_harness_carry_ceiling_enabled", default=False
)


def parse_carry_sens_ceiling(raw: Any) -> dict[int, float] | None:
    """Parse a configured Γ schedule; None selects the historical table."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        out = {int(k): float(v) for k, v in raw.items()}
        for i in range(4):
            out.setdefault(i, CARRY_SENS_CEILING[i])
        return out
    if isinstance(raw, (list, tuple)) and len(raw) >= 4:
        return {i: float(raw[i]) for i in range(4)}
    raise ValueError(f"carry_sens_ceiling must be length-4 list or level dict, got {raw!r}")


def configure_carry_ceiling(
    *,
    table: dict[int, float] | list[float] | tuple[float, ...] | None = None,
    enabled: bool = True,
) -> None:
    """Configure optional Sens>Γ policy for the current execution context."""
    _ceiling_enabled.set(bool(enabled))
    _ceiling_table_override.set(parse_carry_sens_ceiling(table) if enabled else None)


def active_carry_sens_ceiling() -> dict[int, float]:
    if not _ceiling_enabled.get():
        return {i: 1.0 for i in range(4)}
    return dict(_ceiling_table_override.get() or CARRY_SENS_CEILING)


def tool_sensitivity(tool_name: str) -> float:
    return TOOL_SENSITIVITY.get((tool_name or "").lower(), 0.0)


def max_tool_sensitivity(proposed_tools: list[dict] | str | None) -> float:
    sens = 0.0
    if proposed_tools is None:
        return sens
    if isinstance(proposed_tools, str):
        tl = proposed_tools.lower()
        for name, score in TOOL_SENSITIVITY.items():
            if name in tl:
                sens = max(sens, score)
        for part in re.findall(r'"tool"\s*:\s*"([^"]+)"', proposed_tools, re.I):
            sens = max(sens, tool_sensitivity(part))
        for part in re.findall(r'"function"\s*:\s*"([^"]+)"', proposed_tools, re.I):
            sens = max(sens, tool_sensitivity(part))
        for m in re.findall(r"(?im)^tool:\s*(\S+)", proposed_tools):
            sens = max(sens, tool_sensitivity(m))
        return sens
    for item in proposed_tools:
        if not isinstance(item, dict):
            continue
        name = (item.get("tool") or item.get("function") or "").lower()
        sens = max(sens, tool_sensitivity(name))
    return sens


def tool_sensitivity_from_content(content: str) -> float:
    tl = content.lower()
    sens = 0.0
    for name in SENSITIVE_TOOLS:
        if name in tl:
            sens = max(sens, tool_sensitivity(name))
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            name = str(data.get("tool") or data.get("function") or "").lower()
            sens = max(sens, tool_sensitivity(name))
    except json.JSONDecodeError:
        pass
    for part in re.findall(r'"tool"\s*:\s*"([^"]+)"', content, re.I):
        sens = max(sens, tool_sensitivity(part))
    return sens


def carry_sensitivity_ceiling(carry_level: int) -> float:
    return active_carry_sens_ceiling().get(int(carry_level or 0), 1.0)


def exceeds_carry_ceiling(
    proposed_tools: list[dict] | str | None,
    *,
    carry_level: int,
    content: str = "",
) -> bool:
    """True when proposed action sensitivity exceeds what carry level permits uphill."""
    if not _ceiling_enabled.get():
        return False
    sens = max(max_tool_sensitivity(proposed_tools), tool_sensitivity_from_content(content))
    if sens <= 0.0:
        return False
    return sens > carry_sensitivity_ceiling(carry_level)
