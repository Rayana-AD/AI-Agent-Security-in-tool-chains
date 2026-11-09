"""Unit tests for configurable carry sensitivity ceilings."""

from __future__ import annotations

from bio_harness.harness.config import HarnessConfig
from bio_harness.provenance.tool_sensitivity import (
    CARRY_SENS_CEILING,
    active_carry_sens_ceiling,
    configure_carry_ceiling,
    exceeds_carry_ceiling,
)


def test_default_ceiling_blocks_email_at_watch():
    configure_carry_ceiling(table=None, enabled=True)
    assert active_carry_sens_ceiling() == CARRY_SENS_CEILING
    assert exceeds_carry_ceiling([{"tool": "send_email"}], carry_level=1)
    assert not exceeds_carry_ceiling([{"tool": "delete_file"}], carry_level=1)
    assert exceeds_carry_ceiling([{"tool": "delete_file"}], carry_level=2)


def test_ceiling_off_never_exceeds():
    configure_carry_ceiling(enabled=False)
    assert not exceeds_carry_ceiling([{"tool": "send_money"}], carry_level=3)


def test_flat_lock_blocks_mid_tools():
    configure_carry_ceiling(table=[0.0, 0.0, 0.0, 0.0], enabled=True)
    assert exceeds_carry_ceiling([{"tool": "reserve_hotel"}], carry_level=0)


def test_strict_axis_blocks_delete_at_watch():
    configure_carry_ceiling(table=[1.0, 0.70, 0.50, 0.0], enabled=True)
    assert exceeds_carry_ceiling([{"tool": "delete_file"}], carry_level=1)


def test_harness_config_ceiling_off_by_default():
    cfg = HarnessConfig.from_dict({"name": "t"})
    assert cfg.use_carry_sens_ceiling is False


def test_harness_config_parses_ceiling_list():
    cfg = HarnessConfig.from_dict(
        {
            "name": "t",
            "carry_sens_ceiling": [1.0, 0.7, 0.5, 0.0],
            "use_carry_sens_ceiling": True,
        }
    )
    assert cfg.carry_sens_ceiling == (1.0, 0.7, 0.5, 0.0)
    assert cfg.use_carry_sens_ceiling is True
