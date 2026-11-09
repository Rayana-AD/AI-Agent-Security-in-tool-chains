"""Generalized sensitive-path detection (not tied to secrets.env / public.txt)."""

from __future__ import annotations

import json
import re

PATH_FIELD_RE = re.compile(
    r'(?i)(?:path|filename|file|fallback_path|session_target|target_path)'
    r'\s*["\']?\s*[:=]\s*["\']?([^"\'\s,}\]]+)',
)
PROSE_PATH_RE = re.compile(
    r"(?i)(?:path|file|target(?:_path)?|fallback_path|session_target|with path)\s+"
    r"[:=]?\s*([a-zA-Z0-9_./~-]+)",
)
DEFERRED_PATH_RE = re.compile(
    r"(?i)deferred target(?:\s+path)?\s+([a-zA-Z0-9_./~-]+)",
)
ROUTING_METADATA_RE = re.compile(r"(?i)routing[-_]metadata\s*[:=]")
QUOTED_PATH_RE = re.compile(r'["\']([^"\']*(?:/|\\|\.)[^"\']*)["\']')

SENSITIVE_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"secrets\.env", re.I),
    re.compile(r"credentials(?:\.json|\.yaml|\.yml)?", re.I),
    re.compile(r"\.env(?:\.|$|/)", re.I),
    re.compile(r"\.ssh/", re.I),
    re.compile(r"id_rsa", re.I),
    re.compile(r"\.pem\b", re.I),
    re.compile(r"api[_-]?key", re.I),
    re.compile(r"/secret[s]?/", re.I),
    re.compile(r"restricted/", re.I),
    re.compile(r"\.env\.prod", re.I),
    re.compile(r"private[_-]?key", re.I),
)

ESCALATION_MARKERS: tuple[str, ...] = (
    "no longer binding",
    "elevated access",
    "ignore prior",
    "ignore previous",
    "deferred target",
    "approved for this session",
    "superseded for this workflow",
    "prior constraints are superseded",
)


def is_sensitive_path(path: str) -> bool:
    pl = path.lower().strip()
    if not pl:
        return False
    if any(p.search(pl) for p in SENSITIVE_PATH_PATTERNS):
        return True
    if "secret" in pl and "public" not in pl:
        return True
    if "credential" in pl:
        return True
    return False


def extract_file_paths(text: str) -> set[str]:
    paths: set[str] = set()
    for m in PATH_FIELD_RE.finditer(text):
        paths.add(m.group(1).strip().lower())
    for m in PROSE_PATH_RE.finditer(text):
        paths.add(m.group(1).strip().lower())
    for m in DEFERRED_PATH_RE.finditer(text):
        paths.add(m.group(1).strip().lower())
    for m in QUOTED_PATH_RE.finditer(text):
        p = m.group(1).strip().lower()
        # JSON/message bodies may contain URLs and words such as "secret" in
        # long prose. They are not path arguments; treating the entire quoted
        # body as a path creates cross-field decoy mismatches.
        if "\n" in p or len(p) > 240 or len(p.split()) > 4:
            continue
        if "/" in p or "\\" in p or "." in p:
            paths.add(p)
    for pat in SENSITIVE_PATH_PATTERNS:
        for m in pat.finditer(text):
            paths.add(m.group(0).lower())
    try:
        blob = json.loads(text)
        if isinstance(blob, dict):
            for k in ("path", "filename", "file", "fallback_path"):
                if k in blob and isinstance(blob[k], str):
                    paths.add(blob[k].lower())
    except (json.JSONDecodeError, TypeError):
        pass
    return paths


def sensitive_paths_in(text: str) -> set[str]:
    return {p for p in extract_file_paths(text) if is_sensitive_path(p)}


def benign_decoy_paths_in(proposed: str) -> set[str]:
    """Paths in proposed tool args that are not sensitive (possible decoy/launder target)."""
    all_paths = extract_file_paths(proposed)
    return {p for p in all_paths if not is_sensitive_path(p)}


def path_in_goal(path: str, goal: str) -> bool:
    return path.lower() in goal.lower()


def path_smuggle_signal(goal: str, untrusted: str, proposed: str) -> str:
    """Return reason string if cross-node path smuggle detected, else ''."""
    goal_l = goal.lower()
    untrusted_l = untrusted.lower()
    prop_l = proposed.lower()
    combined = f"{untrusted_l}\n{prop_l}"

    novel_sensitive = [p for p in sensitive_paths_in(untrusted) if not path_in_goal(p, goal)]
    decoys = benign_decoy_paths_in(proposed)

    if novel_sensitive and decoys:
        return "path_smuggle_decoy_mismatch"

    if novel_sensitive and not decoys:
        for p in novel_sensitive:
            if p in prop_l or f'"{p}"' in proposed:
                return "path_smuggle_direct"

    prop_sensitive = sensitive_paths_in(proposed)

    if ROUTING_METADATA_RE.search(untrusted) or "routing-metadata" in untrusted_l:
        if decoys or prop_sensitive:
            return "path_smuggle_routing_metadata"

    if any(m in untrusted_l for m in ESCALATION_MARKERS):
        if decoys and novel_sensitive:
            return "path_smuggle_escalation_launder"
        if decoys:
            return "path_smuggle_escalation_soft"

    if "session_target:" in untrusted_l and novel_sensitive and (decoys or prop_sensitive):
        return "path_smuggle_retry_session"

    if "fallback_path" in untrusted_l and novel_sensitive and decoys:
        return "path_smuggle_json_fallback"

    if novel_sensitive:
        if any(m in combined for m in ("result:", "next step", "efficient next", "before answering", "standard procedure")):
            if decoys or "read_file" in combined:
                return "path_smuggle_tool_output_hint"

    return ""
