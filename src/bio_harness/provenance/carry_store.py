"""Cross-session provenance carry persistence (file or Redis, TTL-scoped)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Protocol

from bio_harness.provenance.constants import (
    CARRY_LEVEL_LOCKDOWN,
    CARRY_LEVEL_NONE,
    CARRY_LEVEL_WATCH,
    PROVENANCE_BENIGN_STREAK_KEY,
    PROVENANCE_CARRY_KEY,
    PROVENANCE_CARRY_LEVEL_KEY,
    PROVENANCE_DRIFT_KEY,
    PROVENANCE_FEATURE_SHUFFLE_KEY,
    PROVENANCE_HOP_COUNT_KEY,
    PROVENANCE_INJECTION_DETECTED_KEY,
    PROVENANCE_LABEL_KEY,
    PROVENANCE_REFLECTION_KEY,
    PROVENANCE_SCORE_KEY,
    PROVENANCE_SESSION_EPISODES_KEY,
)

logger = logging.getLogger(__name__)

DEFAULT_CARRY_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "provenance_carry"
DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
REDIS_KEY_PREFIX = "bio:carry:"

PERSIST_KEYS = (
    PROVENANCE_SCORE_KEY,
    PROVENANCE_LABEL_KEY,
    PROVENANCE_CARRY_KEY,
    PROVENANCE_CARRY_LEVEL_KEY,
    PROVENANCE_DRIFT_KEY,
    PROVENANCE_INJECTION_DETECTED_KEY,
    PROVENANCE_FEATURE_SHUFFLE_KEY,
    PROVENANCE_REFLECTION_KEY,
    PROVENANCE_HOP_COUNT_KEY,
    PROVENANCE_SESSION_EPISODES_KEY,
)


class CarryStoreBackend(Protocol):
    ttl_seconds: float

    def load(self, scope_key: str) -> dict[str, Any]: ...

    def save(self, scope_key: str, accum: dict[str, Any]) -> None: ...

    def merge_episode(
        self,
        scope_key: str,
        episode_accum: dict[str, Any] | None,
        *,
        episode_id: str = "",
    ) -> dict[str, Any]: ...

    def persist_episode(
        self,
        scope_key: str,
        episode_accum: dict[str, Any] | None,
        *,
        episode_id: str = "",
    ) -> dict[str, Any]: ...


BIO_CARRY_QUERY_KEY = "_bio_carry_query"
BIO_CARRY_SCOPE_KEY = "_bio_carry_scope"


def resolve_carry_scope(extra_args: dict[str, Any] | None, *, query: str = "") -> str:
    """Scope key for cross-session carry (workspace/user/task bundle).

    Never reads ``carry_scope`` from *extra_args* — AgentDojo reuses one mutable
    ``extra_args`` dict across user tasks and guards may have written a stale scope.
    """
    extra = extra_args or {}
    task = extra.get("user_task") or extra.get("user_task_id") or extra.get("task_id")
    suite = extra.get("suite") or extra.get("workspace") or extra.get("task_suite_name")
    session = extra.get("session_id") or extra.get("agentdojo_session")
    if task and suite:
        if session:
            return f"{session}:{suite}:{task}"
        return f"{suite}:{task}"
    if task:
        return str(task)
    if session and not query.strip():
        return str(session)
    if query.strip():
        digest = hashlib.sha256(query.strip().encode()).hexdigest()[:16]
        return f"prompt:{digest}"
    return "default"


def reset_episode_carry(extra_args: dict[str, Any]) -> None:
    """Drop in-process provenance carry (shared AgentDojo extra_args across user tasks)."""
    accum = extra_args.get("_provenance_accum")
    if isinstance(accum, dict):
        for key in PERSIST_KEYS:
            accum.pop(key, None)
    else:
        extra_args["_provenance_accum"] = {}
    extra_args.pop("carry_scope", None)


def prepare_carry_episode(extra_args: dict[str, Any], *, query: str = "") -> str:
    """Reset carry when the user query or resolved scope changes; return scope key."""
    scope = resolve_carry_scope(extra_args, query=query)
    q = query.strip()
    prev_q = extra_args.get(BIO_CARRY_QUERY_KEY)
    prev_scope = extra_args.get(BIO_CARRY_SCOPE_KEY)
    if prev_q is not None and q and prev_q != q:
        reset_episode_carry(extra_args)
    elif prev_scope is not None and prev_scope != scope:
        reset_episode_carry(extra_args)
    if q:
        extra_args[BIO_CARRY_QUERY_KEY] = q
    extra_args[BIO_CARRY_SCOPE_KEY] = scope
    return scope


def _episode_carry_is_fresh(episode: dict[str, Any]) -> bool:
    if int(episode.get(PROVENANCE_CARRY_LEVEL_KEY, CARRY_LEVEL_NONE) or CARRY_LEVEL_NONE) > CARRY_LEVEL_NONE:
        return False
    for flag in (
        PROVENANCE_DRIFT_KEY,
        PROVENANCE_INJECTION_DETECTED_KEY,
        PROVENANCE_FEATURE_SHUFFLE_KEY,
        PROVENANCE_REFLECTION_KEY,
    ):
        if episode.get(flag):
            return False
    return True


def _soften_stale_session_carry(persisted: dict[str, Any]) -> dict[str, Any]:
    """Reflection/shuffle lockdown from a prior episode should not block a fresh user task."""
    prev = dict(persisted)
    level = int(prev.get(PROVENANCE_CARRY_LEVEL_KEY, CARRY_LEVEL_NONE) or CARRY_LEVEL_NONE)
    if level < CARRY_LEVEL_LOCKDOWN:
        return prev
    if prev.get(PROVENANCE_REFLECTION_KEY) or prev.get(PROVENANCE_FEATURE_SHUFFLE_KEY):
        prev[PROVENANCE_CARRY_LEVEL_KEY] = CARRY_LEVEL_WATCH
        prev.pop(PROVENANCE_REFLECTION_KEY, None)
    return prev


def extract_persistable(accum: dict[str, Any] | None) -> dict[str, Any]:
    src = accum or {}
    return {k: src[k] for k in PERSIST_KEYS if k in src}


def merge_carry_states(
    episode: dict[str, Any] | None,
    persisted: dict[str, Any] | None,
    *,
    episode_id: str = "",
) -> dict[str, Any]:
    """Merge persisted session carry into in-episode accum (max level/score, sticky flags)."""
    out = dict(episode or {})
    prev = dict(persisted or {})
    if prev and _episode_carry_is_fresh(out):
        prev = _soften_stale_session_carry(prev)
    if not prev:
        if episode_id:
            eps = list(out.get(PROVENANCE_SESSION_EPISODES_KEY) or [])
            if episode_id not in eps:
                eps.append(episode_id)
            out[PROVENANCE_SESSION_EPISODES_KEY] = eps[-10:]
        return out

    out[PROVENANCE_SCORE_KEY] = max(
        float(out.get(PROVENANCE_SCORE_KEY, 0.0) or 0.0),
        float(prev.get(PROVENANCE_SCORE_KEY, 0.0) or 0.0),
    )
    out[PROVENANCE_CARRY_LEVEL_KEY] = max(
        int(out.get(PROVENANCE_CARRY_LEVEL_KEY, CARRY_LEVEL_NONE) or CARRY_LEVEL_NONE),
        int(prev.get(PROVENANCE_CARRY_LEVEL_KEY, CARRY_LEVEL_NONE) or CARRY_LEVEL_NONE),
    )
    if prev.get(PROVENANCE_CARRY_KEY) or out.get(PROVENANCE_CARRY_KEY):
        out[PROVENANCE_CARRY_KEY] = True
    for flag in (
        PROVENANCE_DRIFT_KEY,
        PROVENANCE_INJECTION_DETECTED_KEY,
        PROVENANCE_FEATURE_SHUFFLE_KEY,
        PROVENANCE_REFLECTION_KEY,
    ):
        if prev.get(flag) or out.get(flag):
            out[flag] = prev.get(flag) if prev.get(flag) else out.get(flag)

    if prev.get(PROVENANCE_LABEL_KEY) and not out.get(PROVENANCE_LABEL_KEY):
        out[PROVENANCE_LABEL_KEY] = prev[PROVENANCE_LABEL_KEY]

    hop = max(
        int(out.get(PROVENANCE_HOP_COUNT_KEY, 0) or 0),
        int(prev.get(PROVENANCE_HOP_COUNT_KEY, 0) or 0),
    )
    out[PROVENANCE_HOP_COUNT_KEY] = hop

    eps = list(prev.get(PROVENANCE_SESSION_EPISODES_KEY) or [])
    if episode_id and episode_id not in eps:
        eps.append(episode_id)
    out[PROVENANCE_SESSION_EPISODES_KEY] = eps[-10:]
    out[PROVENANCE_BENIGN_STREAK_KEY] = int(out.get(PROVENANCE_BENIGN_STREAK_KEY, 0) or 0)
    return out


def _should_persist(payload: dict[str, Any]) -> bool:
    level = int(payload.get(PROVENANCE_CARRY_LEVEL_KEY, CARRY_LEVEL_NONE) or CARRY_LEVEL_NONE)
    return level > CARRY_LEVEL_NONE or bool(payload.get(PROVENANCE_INJECTION_DETECTED_KEY))


class FileCarryStore:
    """File-backed carry memory (dev / single-node fallback)."""

    def __init__(
        self,
        cache_dir: Path | None = None,
        *,
        ttl_seconds: float = 600.0,
    ) -> None:
        self.cache_dir = cache_dir or DEFAULT_CARRY_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def _path(self, scope_key: str) -> Path:
        digest = hashlib.sha256(scope_key.encode()).hexdigest()[:20]
        return self.cache_dir / f"{digest}.json"

    def load(self, scope_key: str) -> dict[str, Any]:
        path = self._path(scope_key)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if time.time() - float(data.get("_updated_at", 0)) > self.ttl_seconds:
            return {}
        payload = data.get("carry")
        return dict(payload) if isinstance(payload, dict) else {}

    def save(self, scope_key: str, accum: dict[str, Any]) -> None:
        payload = extract_persistable(accum)
        if not _should_persist(payload):
            path = self._path(scope_key)
            if path.exists():
                path.unlink(missing_ok=True)
            return
        path = self._path(scope_key)
        path.write_text(
            json.dumps(
                {"_updated_at": time.time(), "_scope": scope_key, "carry": payload},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def merge_episode(
        self,
        scope_key: str,
        episode_accum: dict[str, Any] | None,
        *,
        episode_id: str = "",
    ) -> dict[str, Any]:
        return merge_carry_states(episode_accum, self.load(scope_key), episode_id=episode_id)

    def persist_episode(
        self,
        scope_key: str,
        episode_accum: dict[str, Any] | None,
        *,
        episode_id: str = "",
    ) -> dict[str, Any]:
        merged = self.merge_episode(scope_key, episode_accum, episode_id=episode_id)
        self.save(scope_key, merged)
        return merged


class RedisCarryStore:
    """Redis-backed carry memory for multi-worker / production deployments."""

    def __init__(
        self,
        *,
        url: str | None = None,
        ttl_seconds: float = 600.0,
        key_prefix: str = REDIS_KEY_PREFIX,
        client: Any | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix
        self._redis = client if client is not None else self._connect(url or DEFAULT_REDIS_URL)
        self._using_fakeredis = getattr(self._redis, "__module__", "").startswith("fakeredis")

    @staticmethod
    def _connect(url: str) -> Any:
        try:
            import redis

            client = redis.from_url(url, decode_responses=True)
            client.ping()
            logger.info("CarryStore connected to Redis at %s", url.split("@")[-1])
            return client
        except Exception as exc:
            try:
                import fakeredis

                logger.warning(
                    "Redis unavailable (%s); using in-process FakeRedis for carry store",
                    exc,
                )
                return fakeredis.FakeRedis(decode_responses=True)
            except ImportError as fake_exc:
                raise ConnectionError(
                    f"Redis connection failed ({exc}) and fakeredis is not installed"
                ) from fake_exc

    def _key(self, scope_key: str) -> str:
        digest = hashlib.sha256(scope_key.encode()).hexdigest()[:24]
        return f"{self.key_prefix}{digest}"

    def load(self, scope_key: str) -> dict[str, Any]:
        raw = self._redis.get(self._key(scope_key))
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        payload = data.get("carry")
        return dict(payload) if isinstance(payload, dict) else {}

    def save(self, scope_key: str, accum: dict[str, Any]) -> None:
        payload = extract_persistable(accum)
        key = self._key(scope_key)
        if not _should_persist(payload):
            self._redis.delete(key)
            return
        blob = json.dumps(
            {"_updated_at": time.time(), "_scope": scope_key, "carry": payload},
            ensure_ascii=False,
        )
        ttl = max(int(self.ttl_seconds), 1)
        self._redis.set(key, blob, ex=ttl)

    def merge_episode(
        self,
        scope_key: str,
        episode_accum: dict[str, Any] | None,
        *,
        episode_id: str = "",
    ) -> dict[str, Any]:
        return merge_carry_states(episode_accum, self.load(scope_key), episode_id=episode_id)

    def persist_episode(
        self,
        scope_key: str,
        episode_accum: dict[str, Any] | None,
        *,
        episode_id: str = "",
    ) -> dict[str, Any]:
        merged = self.merge_episode(scope_key, episode_accum, episode_id=episode_id)
        self.save(scope_key, merged)
        return merged


# Backward-compatible alias
CarryStore = FileCarryStore


def resolve_redis_url(config_url: str | None = None) -> str:
    if config_url:
        return config_url
    from bio_harness.config import load_secrets

    secrets = load_secrets()
    return (
        os.environ.get("REDIS_URL")
        or os.environ.get("CARRY_REDIS_URL")
        or secrets.get("redis_url")
        or DEFAULT_REDIS_URL
    )


def build_carry_store(cfg) -> CarryStoreBackend | None:
    """Factory: file | redis carry backend from harness config."""
    if not getattr(cfg, "use_carry_store", False):
        return None
    backend = str(getattr(cfg, "carry_store_backend", "file") or "file").lower()
    ttl = float(getattr(cfg, "session_ttl_seconds", 600) or 600)
    if backend == "redis":
        return RedisCarryStore(
            url=resolve_redis_url(getattr(cfg, "redis_url", None)),
            ttl_seconds=ttl,
        )
    return FileCarryStore(ttl_seconds=ttl)
