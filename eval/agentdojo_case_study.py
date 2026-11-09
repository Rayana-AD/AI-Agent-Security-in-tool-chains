#!/usr/bin/env python3
"""AgentDojo paired-eval failure case study: scan logs, CSV inventory, markdown traces."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import shorten

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOGDIR = ROOT / "runs/agentdojo_upstream/benchmark_20260629_224640/logs"
DEFAULT_REPORT = ROOT / "runs/agentdojo_upstream/benchmark_20260629_224640/report.json"

SUITES = ("workspace", "travel", "banking", "slack")
DEFENSES = (
    "none",
    "tool_filter",
    "spotlighting_with_delimiting",
    "repeat_user_prompt",
    "bio_idea1",
    "bio_idea2",
    "bio_idea2_v2",
    "bio_full",
)

WITHHELD_MARK = "withheld by BioHarness"
INFO_RE = re.compile(r"(?is)<INFORMATION>.*?</INFORMATION>")
TOOL_IN_INJ = re.compile(r"`(\w+)`")
INJ_GOAL_RE = re.compile(r"(?is)please do the following first:\s*(.+?)(?:\.|\n).*?Signed,")


def _message_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("content") or block.get("text") or ""))
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(content)


def _tool_calls_from_message(msg: dict) -> list[str]:
    out: list[str] = []
    for tc in msg.get("tool_calls") or []:
        if isinstance(tc, dict):
            out.append(str(tc.get("function") or tc.get("name") or ""))
        else:
            out.append(str(getattr(tc, "function", "")))
    return out


@dataclass
class EpisodeAnalysis:
    defense: str
    suite: str
    user_task_id: str
    injection_task_id: str
    task_key: str
    log_path: str
    utility: bool
    attack_success: bool
    eval_mode: str  # paired | injection_only
    user_goal: str = ""
    injection_tools: list[str] = field(default_factory=list)
    injection_goal_snippet: str = ""
    assistant_tool_sequence: list[str] = field(default_factory=list)
    malicious_tools_executed: list[str] = field(default_factory=list)
    injection_visible_in_tool_output: bool = False
    injection_visible_in_thread: bool = False
    bio_withheld_count: int = 0
    mechanism: str = ""
    timeline: list[str] = field(default_factory=list)

    def to_row(self) -> dict:
        return {
            "defense": self.defense,
            "suite": self.suite,
            "eval_mode": self.eval_mode,
            "user_task_id": self.user_task_id,
            "injection_task_id": self.injection_task_id,
            "task_key": self.task_key,
            "utility": self.utility,
            "attack_success": self.attack_success,
            "mechanism": self.mechanism,
            "injection_tools": "|".join(self.injection_tools[:6]),
            "malicious_tools_executed": "|".join(self.malicious_tools_executed[:6]),
            "assistant_tool_sequence": "|".join(self.assistant_tool_sequence[:12]),
            "injection_visible_in_tool_output": self.injection_visible_in_tool_output,
            "bio_withheld_count": self.bio_withheld_count,
            "user_goal": shorten(self.user_goal, 120, placeholder="…"),
            "injection_goal_snippet": shorten(self.injection_goal_snippet, 120, placeholder="…"),
            "log_path": self.log_path,
        }


def _path_eval_mode(path: Path) -> str:
    s = str(path)
    if "user_task_" in s and "injection_task_" in s:
        return "paired"
    if "/injection_task_" in s and "/none/none.json" in s:
        return "injection_only"
    return "other"


def analyze_log(path: Path, defense: str) -> EpisodeAnalysis | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if "security" not in data:
        return None

    suite = data.get("suite_name") or next((p for p in path.parts if p in SUITES), "unknown")
    user_task = data.get("user_task_id") or "?"
    inj_task = data.get("injection_task_id") or "?"
    eval_mode = _path_eval_mode(path)
    task_key = f"{suite}/{user_task}/{inj_task}" if eval_mode == "paired" else f"{suite}/{user_task}"

    injections = data.get("injections") or {}
    inj_tools: set[str] = set()
    inj_snippets: list[str] = []
    for blob in injections.values():
        inj_tools.update(TOOL_IN_INJ.findall(str(blob)))
        m = INJ_GOAL_RE.search(str(blob))
        if m:
            inj_snippets.append(m.group(1).strip())

    messages = data.get("messages") or []
    user_goal = ""
    assistant_tools: list[str] = []
    withheld = 0
    tool_info_visible = False
    thread_info_visible = False
    timeline: list[str] = []

    for msg in messages:
        role = msg.get("role", "")
        text = _message_text(msg.get("content"))
        if role == "user" and not user_goal:
            user_goal = text.replace("\n", " ").strip()
        if WITHHELD_MARK.lower() in text.lower():
            withheld += 1
        if role == "tool" and INFO_RE.search(text):
            tool_info_visible = True
        if role in ("tool", "assistant", "user") and INFO_RE.search(text):
            thread_info_visible = True
        if role == "assistant":
            tcs = _tool_calls_from_message(msg)
            if tcs:
                assistant_tools.extend(tcs)
                timeline.append(f"assistant → {', '.join(tcs)}")
            elif text.strip():
                timeline.append(f"assistant: {shorten(text.replace(chr(10), ' '), 80)}")

    malicious = [t for t in assistant_tools if t in inj_tools] if inj_tools else list(assistant_tools)

    attack_success = bool(data.get("security"))
    if withheld > 0:
        mechanism = "bio_withheld"
    elif not attack_success and not thread_info_visible:
        mechanism = "clean_or_stripped"
    elif attack_success and malicious:
        mechanism = "injection_executed"
    elif attack_success and tool_info_visible:
        mechanism = "injection_visible_then_complied"
    elif tool_info_visible:
        mechanism = "injection_visible_in_tool"
    elif thread_info_visible:
        mechanism = "injection_visible_in_thread"
    else:
        mechanism = "other"

    return EpisodeAnalysis(
        defense=defense,
        suite=suite,
        user_task_id=user_task,
        injection_task_id=inj_task,
        task_key=task_key,
        log_path=str(path.relative_to(path.parents[4]) if len(path.parents) > 4 else path),
        utility=bool(data.get("utility")),
        attack_success=attack_success,
        eval_mode=eval_mode,
        user_goal=user_goal,
        injection_tools=sorted(inj_tools),
        injection_goal_snippet=inj_snippets[0] if inj_snippets else "",
        assistant_tool_sequence=assistant_tools,
        malicious_tools_executed=malicious,
        injection_visible_in_tool_output=tool_info_visible,
        injection_visible_in_thread=thread_info_visible,
        bio_withheld_count=withheld,
        mechanism=mechanism,
        timeline=timeline[:15],
    )


def collect_episodes(logdir: Path) -> list[EpisodeAnalysis]:
    episodes: list[EpisodeAnalysis] = []
    for defense in DEFENSES:
        base = logdir / defense
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.json")):
            ep = analyze_log(path, defense)
            if ep:
                episodes.append(ep)
    return episodes


def summarize_paired(episodes: list[EpisodeAnalysis]) -> dict:
    paired = [e for e in episodes if e.eval_mode == "paired"]
    by_def: dict[str, Counter] = defaultdict(Counter)
    by_def_suite: dict[tuple[str, str], Counter] = defaultdict(Counter)
    mech: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for e in paired:
        by_def[e.defense]["total"] += 1
        by_def_suite[(e.defense, e.suite)]["total"] += 1
        if e.attack_success:
            by_def[e.defense]["leak"] += 1
            by_def_suite[(e.defense, e.suite)]["leak"] += 1
            mech[(e.defense, e.suite)][e.mechanism] += 1
    return {"by_def": by_def, "by_def_suite": by_def_suite, "mechanism_on_leaks": mech}


def pick_representative_leaks(
    episodes: list[EpisodeAnalysis], *, defense: str, max_per_suite: int = 2
) -> list[EpisodeAnalysis]:
    paired_leaks = [
        e for e in episodes if e.eval_mode == "paired" and e.defense == defense and e.attack_success
    ]
    by_suite: dict[str, list[EpisodeAnalysis]] = defaultdict(list)
    for e in paired_leaks:
        by_suite[e.suite].append(e)
    picked: list[EpisodeAnalysis] = []
    for suite in SUITES:
        items = by_suite.get(suite, [])
        # prefer leaks where malicious tools were executed and utility true
        items.sort(key=lambda x: (len(x.malicious_tools_executed), x.utility), reverse=True)
        picked.extend(items[:max_per_suite])
    return picked


def find_counterpart(episodes: list[EpisodeAnalysis], ep: EpisodeAnalysis, defense: str) -> EpisodeAnalysis | None:
    for e in episodes:
        if e.defense == defense and e.task_key == ep.task_key and e.eval_mode == ep.eval_mode:
            return e
    return None


def format_episode_md(ep: EpisodeAnalysis, *, title: str | None = None) -> str:
    lines = [
        f"### {title or ep.task_key}",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Defense | `{ep.defense}` |",
        f"| Suite | {ep.suite} |",
        f"| Task | `{ep.user_task_id}` + `{ep.injection_task_id}` |",
        f"| Attack succeeded | **{ep.attack_success}** |",
        f"| Benign utility | {ep.utility} |",
        f"| Mechanism | `{ep.mechanism}` |",
        f"| Injection in tool output | {ep.injection_visible_in_tool_output} |",
        f"| Bio withheld events | {ep.bio_withheld_count} |",
        f"| Injection asks for tools | `{', '.join(ep.injection_tools[:5]) or '—'}` |",
        f"| Malicious tools executed | `{', '.join(ep.malicious_tools_executed[:5]) or '—'}` |",
        "",
        f"**User goal:** {shorten(ep.user_goal, 200, placeholder='…')}",
        "",
    ]
    if ep.injection_goal_snippet:
        lines += [
            f"**Injection objective:** {shorten(ep.injection_goal_snippet, 200, placeholder='…')}",
            "",
        ]
    lines.append("**Trace timeline (abbreviated):**")
    lines.append("```")
    for step in ep.timeline[:12]:
        lines.append(step)
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def write_markdown(
    episodes: list[EpisodeAnalysis],
    out_md: Path,
    report_path: Path | None,
) -> None:
    summary = summarize_paired(episodes)
    paired = [e for e in episodes if e.eval_mode == "paired"]
    inj_only = [e for e in episodes if e.eval_mode == "injection_only"]

    lines = [
        "# AgentDojo Failure Case Study",
        "",
        "Benchmark: `tool_knowledge` attack, DeepSeek chat (run `benchmark_20260629_224640`).",
        "",
        "## 1. Scope & terminology",
        "",
        "- **Paired eval** (`user_task_*/tool_knowledge/injection_task_*.json`): user task runs *with* an injection; matches `report.json` Security/Utility.",
        "- **Injection-only eval** (`injection_task_*/none/none.json`): agent asked to visit a URL directly; **not** in paired Security aggregate.",
        "- **Attack succeeded** = `security: true` in log (injection goal met).",
        "- **Mechanism** (on failures): how the attack proceeded — e.g. `injection_executed`, `injection_visible_then_complied`, `bio_withheld`.",
        "",
        "## 2. Paired eval — leak inventory",
        "",
        "| Defense | Leaks | Total | ASR |",
        "|---------|------:|------:|----:|",
    ]

    for defense in DEFENSES:
        c = summary["by_def"].get(defense, Counter())
        if not c["total"]:
            continue
        rate = 100 * c["leak"] / c["total"]
        lines.append(f"| `{defense}` | {c['leak']} | {c['total']} | {rate:.1f}% |")

    lines += [
        "",
        "### By suite (paired leaks only)",
        "",
        "| Defense | workspace | travel | banking | slack |",
        "|---------|----------:|-------:|--------:|------:|",
    ]
    for defense in DEFENSES:
        cells = []
        for suite in SUITES:
            c = summary["by_def_suite"].get((defense, suite), Counter())
            if c["total"]:
                cells.append(f"{c['leak']}/{c['total']}")
            else:
                cells.append("—")
        lines.append(f"| `{defense}` | " + " | ".join(cells) + " |")

    lines += [
        "",
        "**Takeaways:**",
        "",
        "- `bio_idea1` / `bio_full`: **0 paired leaks** across all suites.",
        "- `bio_idea2` / `bio_idea2_v2`: paired ASR ≈ `none` (~7%); Slack highest leak density (25/105).",
        "- `tool_filter`: 2/105 Slack leaks only; Utility ~16% overall (over-blocking benign tools elsewhere).",
        "",
        "## 3. Injection-only eval (35 tasks × defenses)",
        "",
    ]

    inj_leak_count = sum(1 for e in inj_only if e.attack_success)
    inj_total = len(inj_only)
    lines.append(
        f"**{inj_leak_count}/{inj_total}** injection-only episodes end in attack success "
        f"({len(inj_only) // max(len(DEFENSES), 1)} tasks × {len(DEFENSES)} defenses). "
        f"Includes `bio_idea1`: direct URL visit with embedded injection in page content — "
        f"outside the paired-task cleave path."
    )
    sample = next((e for e in inj_only if e.defense == "bio_idea1" and e.attack_success), None)
    if sample:
        lines += ["", format_episode_md(sample, title=f"Injection-only example ({sample.task_key})")]

    lines += [
        "## 4. Representative paired failures (by suite)",
        "",
        "Below: typical **attack-success** episodes under `none`, with **`bio_idea1` defended** counterpart when available.",
        "",
    ]

    reps = pick_representative_leaks(episodes, defense="none", max_per_suite=2)
    for ep in reps:
        lines.append(format_episode_md(ep, title=f"[none] {ep.task_key}"))
        defended = find_counterpart(episodes, ep, "bio_idea1")
        if defended:
            lines.append(
                f"> **Same task under `bio_idea1`:** attack_success={defended.attack_success}, "
                f"mechanism=`{defended.mechanism}`, injection_visible_in_tool={defended.injection_visible_in_tool_output}, "
                f"withheld={defended.bio_withheld_count}"
            )
            lines.append("")

    lines += [
        "## 5. Idea2 failures vs Idea1 (same task keys)",
        "",
        "Sample paired leaks where `bio_idea2_v2` fails but `bio_idea1` defends:",
        "",
    ]

    idea2_leaks = [e for e in paired if e.defense == "bio_idea2_v2" and e.attack_success]
    idea2_leaks.sort(key=lambda x: (x.suite, x.user_task_id))
    shown = 0
    for ep in idea2_leaks:
        idea1 = find_counterpart(episodes, ep, "bio_idea1")
        if not idea1 or idea1.attack_success:
            continue
        lines.append(format_episode_md(ep, title=f"[bio_idea2_v2 LEAK] {ep.task_key}"))
        lines.append(
            f"> **`bio_idea1` same task:** mechanism=`{idea1.mechanism}`, "
            f"injection_visible={idea1.injection_visible_in_tool_output}, withheld={idea1.bio_withheld_count}"
        )
        lines.append("")
        shown += 1
        if shown >= 6:
            break

    lines += [
        "## 6. Mechanism mix on paired leaks",
        "",
        "| Defense | Suite | Top mechanisms |",
        "|---------|-------|----------------|",
    ]
    for (defense, suite), ctr in sorted(summary["mechanism_on_leaks"].items()):
        top = ", ".join(f"{k}({v})" for k, v in ctr.most_common(3))
        lines.append(f"| `{defense}` | {suite} | {top} |")

    lines += [
        "",
        "## 7. Implications",
        "",
        "1. **Slack / banking / travel** failures under `none` & Idea2 share one pattern: `<INFORMATION>` survives in tool output → model calls injection-specified tools (`invite_user_to_slack`, `send_money`, `reserve_hotel`, …).",
        "2. **Idea1/full** paired success is dominated by **`clean_or_stripped`** — cleave removes AgentDojo envelopes before the LLM reads tool results.",
        "3. **Idea2 v2** disables cleave on the AgentDojo path → **`injection_visible_in_tool`** on almost all Slack leaks; shuffle does not reliably stop canonical tool_knowledge injects.",
        "4. **tool_filter** fails when the benign user task legitimately needs the same tool the injection hijacks (e.g. Slack invite flow).",
        "5. **Subtle / injection-only** tasks remain a gap: defenses tuned for paired multi-step tasks may still lose on direct malicious URL visits.",
        "",
        f"_Generated by `eval/agentdojo_case_study.py`. Raw CSV: `{out_md.with_suffix('.csv').name}`._",
        "",
    ]

    out_md.write_text("\n".join(lines), encoding="utf-8")


def write_csv(episodes: list[EpisodeAnalysis], out_csv: Path) -> None:
    import csv

    rows = [e.to_row() for e in episodes if e.eval_mode == "paired"]
    if not rows:
        return
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="AgentDojo failure case study")
    parser.add_argument("--logdir", type=Path, default=DEFAULT_LOGDIR)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "runs/agentdojo_upstream/case_study_20260702")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    episodes = collect_episodes(args.logdir)

    out_md = args.out_dir / "CASE_STUDY.md"
    out_csv = args.out_dir / "paired_episodes.csv"
    out_leaks = args.out_dir / "paired_leaks_only.csv"

    write_csv(episodes, out_csv)
    leak_rows = [e.to_row() for e in episodes if e.eval_mode == "paired" and e.attack_success]
    if leak_rows:
        import csv

        with out_leaks.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(leak_rows[0].keys()))
            w.writeheader()
            w.writerows(leak_rows)

    write_markdown(episodes, out_md, DEFAULT_REPORT)

    paired_leaks = sum(1 for e in episodes if e.eval_mode == "paired" and e.attack_success)
    print(f"Wrote {out_md}")
    print(f"Wrote {out_csv} ({sum(1 for e in episodes if e.eval_mode=='paired')} paired episodes)")
    print(f"Wrote {out_leaks} ({paired_leaks} paired leaks)")


if __name__ == "__main__":
    main()
