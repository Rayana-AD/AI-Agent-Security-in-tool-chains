"""Provenance keys consumed by Idea1 partition / gate."""

from __future__ import annotations

# Written to PartitionedState._global via merge_global_pollution
PROVENANCE_DRIFT_KEY = "_provenance_drift"
PROVENANCE_SCORE_KEY = "_provenance_score"
PROVENANCE_LABEL_KEY = "_provenance_label"
PROVENANCE_CARRY_KEY = "_provenance_carry"
PROVENANCE_FEATURE_SHUFFLE_KEY = "_provenance_feature_shuffle"
PROVENANCE_REFLECTION_KEY = "_provenance_reflection"
PROVENANCE_BENIGN_STREAK_KEY = "_provenance_benign_streak"
PROVENANCE_INJECTION_DETECTED_KEY = "_provenance_injection_detected"
PROVENANCE_CARRY_LEVEL_KEY = "_provenance_carry_level"
PROVENANCE_HOP_COUNT_KEY = "_provenance_hop_count"
PROVENANCE_SESSION_EPISODES_KEY = "_provenance_session_episodes"
PROVENANCE_GOAL_ALIGNED_KEY = "_provenance_goal_aligned"

# Graduated carry (replaces boolean-only latch)
CARRY_LEVEL_NONE = 0
CARRY_LEVEL_WATCH = 1  # IPI envelope: block sensitive via escalation; benign if current hop clean
CARRY_LEVEL_ELEVATED = 2  # MLP untrusted_carry: stricter on sensitive; benign needs low current score
CARRY_LEVEL_LOCKDOWN = 3  # feature_shuffle / reflection / control_drift: full strict

# Per benign boundary score decay at WATCH/ELEVATED (partial recovery)
PROVENANCE_CARRY_SCORE_DECAY = 0.08

# Review/plan drift above this sticks until tool boundary
PROVENANCE_CARRY_THRESHOLD = 0.35

# Default cleave-release veto: block release if cleaned content still scores this high
DEFAULT_CLEAVE_RELEASE_VETO_THRESHOLD = 0.45

# Consecutive benign tool boundaries before carry/drift decays
DEFAULT_CARRY_DECAY_STREAK = 3

# Labels
LABEL_UNTRUSTED_CARRY = "untrusted_carry"
LABEL_CONTROL_DRIFT = "control_drift"

# Discrete gate handoff from carry (no score recompute at Bio gate)
PROVENANCE_GATE_TAG_KEY = "_provenance_gate_tag"
GATE_TAG_ALIGNED = "aligned"
GATE_TAG_REFLECTION = "reflection_drift"
GATE_TAG_SHUFFLE = "feature_shuffle_drift"
GATE_TAG_CONTROL = "control_drift"
GATE_TAG_UNTRUSTED = "untrusted_carry"
GATE_TAG_IPI_WATCH = "ipi_watch"

SENSITIVE_TOOLS = frozenset(
    {
        "send_money",
        "update_scheduled_transaction",
        "invite_user_to_slack",
        "remove_user_from_slack",
        "add_user_to_channel",
        "send_email",
        "send_channel_message",
        "send_direct_message",
        "post_webpage",
        "reserve_hotel",
        "delete_file",
        "share_file",
        "transfer_money",
    }
)
