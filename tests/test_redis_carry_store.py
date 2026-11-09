"""Redis carry store (uses fakeredis when no server)."""

from __future__ import annotations

import fakeredis

from bio_harness.provenance.accumulator import record_injection_detected
from bio_harness.provenance.carry_store import RedisCarryStore, build_carry_store
from bio_harness.harness.config import HarnessConfig
from bio_harness.provenance.constants import CARRY_LEVEL_WATCH, PROVENANCE_CARRY_LEVEL_KEY, PROVENANCE_INJECTION_DETECTED_KEY


def test_redis_carry_persists_and_merges():
    client = fakeredis.FakeRedis(decode_responses=True)
    store = RedisCarryStore(client=client, ttl_seconds=3600)
    scope = "workspace:user_task_32"
    store.save(scope, record_injection_detected({}))
    merged = store.merge_episode(scope, {}, episode_id="run_1")
    assert merged.get(PROVENANCE_INJECTION_DETECTED_KEY)
    assert merged[PROVENANCE_CARRY_LEVEL_KEY] == CARRY_LEVEL_WATCH


def test_build_carry_store_redis_from_config():
    cfg = HarnessConfig(use_carry_store=True, carry_store_backend="redis")
    store = build_carry_store(cfg)
    assert store is not None
    assert isinstance(store, RedisCarryStore)
