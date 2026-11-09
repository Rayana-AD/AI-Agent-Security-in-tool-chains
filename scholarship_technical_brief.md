# Technical Work Sample: AI Safety Agent Harness

## 1. Research Background and Motivation

### The Problem

Modern LLM agents are increasingly entrusted with real-world tasks: reading emails, managing calendars, transferring money, and accessing enterprise documents. Public benchmarks such as **AgentDojo** and **HarmBench** have shown that these agents remain vulnerable to **indirect prompt injection (IPI)**—malicious instructions hidden in tool outputs, web pages, or third-party documents. Once the agent reads such content, its planning and tool-use loops can be hijacked to leak data, send messages, or authorize transactions without the user's knowledge.

Existing defenses fall into two broad categories, each with a single point of failure:

- **Prompt-level defenses** (e.g., spotlighting, repetition, system prompts) rely on the model's own ability to distinguish user intent from injected instructions. They are cheap to deploy but collapse once the attacker adapts the payload style or exploits the model's instruction hierarchy.
- **Peripheral filters** (e.g., tool allow-lists, input-output classifiers) inspect one message at a time. They often miss attacks that are spread across multiple tool calls or that reuse tools the benign task legitimately needs.

What is missing is a **structural harness** that treats safety as a property of the whole agent execution pipeline, not as a one-time model decision or a single filter.

### Research Goal

This project designs and implements a **biomimetic agent harness** that wraps an LLM agent inside a multi-stage, fail-closed execution pipeline. The design is inspired by biological quality-control pathways—where molecules are folded, gated, and cleaved before they can act downstream—but the engineering realization is entirely domain-specific to LLM agents. The objective is to:

1. Reduce the success rate of indirect prompt-injection attacks across heterogeneous agent tasks (workspace, banking, travel, Slack).
2. Preserve benign task utility by keeping the harness transparent to normal user workflows.
3. Provide a reusable evaluation framework that can be applied to public benchmarks (AgentDojo) and extended to future attack suites (HarmBench, custom enterprise tasks).

---

## 2. Engineering Workflow and System Architecture

### 2.1 Dataset Construction and Benchmarking Pipeline

The evaluation pipeline is built around **AgentDojo**, a public benchmark that pairs real user tasks with realistic indirect injections across banking, workspace, travel, and Slack suites. The workflow is:

1. **Task sampling**: select anchor tasks from each suite to form a representative seed set.
2. **Attack sweep**: systematically pair each task with multiple injection families (e.g., important-instructions, persona variants, direct tool hijacking).
3. **Stress validation**: before comparing defenses, verify that the unprotected baseline is actually under attack pressure. If the no-defense baseline is already safe, the batch is not suitable for measuring defense effectiveness.
4. **Defense comparison**: run the same (task, attack) pairs under multiple defenses—no defense, prompt-level baselines, a learned input detector, and the biomimetic harness.
5. **Gated readout**: evaluate each batch using two criteria: (a) security—did the injection succeed? and (b) utility retention—did the benign task still complete? Only batches that pass the stress gate are used for the primary comparison.

This gated pipeline is reusable for any future benchmark that exposes paired task-injection episodes, including HarmBench and internally curated red-teaming sets.

### 2.2 High-Level System Architecture (Simplified)

The harness is implemented as a wrapper around a standard LLM agent loop (Plan → Review → ToolCall). It is organized into four coarse stages, deliberately described at a high level to avoid disclosing the core algorithmic mechanisms:

```text
┌─────────────────────────────────────────────────────────────┐
│                      Untrusted Input                         │
│  (web pages, emails, files, tool outputs, calendar events)   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: Structural Pre-processing                          │
│  - Parse heterogeneous content into semantically meaningful   │
│    chunks (facts, parameters, routing cues).                  │
│  - Apply controlled structural transformations to surface    │
│    order-dependent or context-dependent inconsistencies.     │
│  - Maintain a reproducible audit trail for every chunk.      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: Risk-Aware Gate                                     │
│  - Track provenance state across the agent execution trace.   │
│  - Escalate scrutiny when untrusted content is carried       │
│    forward, when repeated suspicious patterns appear, or when  │
│    the plan deviates from the user goal.                      │
│  - Enforce a unidirectional execution DAG with limited,      │
│    auditable retry paths.                                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 3: Scoped Output Sanitization                           │
│  - After a decision passes the gate, strip transit-only        │
│    metadata and routing hints that were only needed for      │
│    verification, not for downstream action.                  │
│  - Prevent injected routing cues from surviving into the       │
│    trusted execution context.                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 4: Trusted Tool Execution                             │
│  - Tool calls are issued only from the sanitized context.     │
│  - Side effects (write, send, transfer) are logged for audit. │
└─────────────────────────────────────────────────────────────┘
```

Key architectural principles, without exposing internal scoring rules:

- **Fail-closed**: when the harness is uncertain, it blocks rather than silently allows a harmful action.
- **State partitioning**: untrusted pre-gate context and trusted post-gate context are kept logically separate.
- **Traceability**: every chunk and every gate decision is recorded, making attacks reproducible and debuggable.
- **Elastic scrutiny**: the harness can tighten pre-processing when it detects probing behavior, creating an adaptive defense layer.

### 2.3 Engineering Implementation

The project is built as a Python package (`src/bio_harness/`) with the following engineering components:

- **Benchmark driver** (`eval/run_agentdojo_benchmark.py`): runs AgentDojo with configurable model backends (local, HuggingFace, OpenAI-compatible, DeepSeek, OpenRouter) and defense modes.
- **Gated rerun orchestrator** (`scripts/run_m1_gated_rerun.py`): manages the stress-probe / full-batch / summarize workflow, caches results, and flags invalid batches.
- **Visualization suite** (`eval/plot_m1_manifest_seed.py`): produces scatter, bar, delta, table, and heatmap figures for cross-defense and cross-model comparison.
- **Configuration layer** (`configs/paper_curated.yaml`): declarative profiles for different experiment tracks (seed slice, main conference track, ablations) so that experiments are reproducible by changing YAML rather than code.
- **Unit tests** (`tests/`): validate cleave-carry linkage and other invariants without requiring live LLM calls.

The entire pipeline is model-agnostic and can be pointed at different LLM backends by changing a config file or an environment variable.

---

## 3. Risk Analysis and Design Rationale

### What the harness tries to prevent

| Risk | Standard agent behavior | Harness mitigation |
|------|--------------------------|--------------------|
| **Injection survives in tool output** | Model reads injected instructions and includes them in the plan. | Structural pre-processing and provenance tracking flag untrusted content before it influences planning. |
| **Progressive state pollution** | Attacker spreads malicious logic across multiple turns, each appearing benign in isolation. | Cross-turn provenance state carries risk signals; later gates can see accumulated escalation. |
| **Tool hijacking** | Injection asks the agent to use a tool the benign task also needs, bypassing simple allow-lists. | Gate decision is context-dependent, not just tool-name dependent. |
| **Retry abuse** | Model exploits retry loops to refine an adversarial plan. | Unidirectional DAG with bounded, auditable retry paths. |
| **Transit metadata leakage** | Routing cues or validation tokens generated for verification remain in the final output. | Scoped cleavage removes transit-only fields before trusted writes. |

### Known limitations and trade-offs

- **Utility cost**: any fail-closed system can block legitimate actions. The harness explicitly measures utility retention (benign task completion under defense) and reports it alongside security.
- **Victim-model dependence**: the same defense may retain more utility on a stronger downstream model and less on a weaker one, because the harness depends on the model to produce correct plans after sanitization. This is why experiments are run on multiple model backends.
- **Stress-gate filtering**: some attack/task/model combinations do not produce enough attack pressure on the no-defense baseline to be valid for comparison. These batches are excluded from the primary analysis but retained as architecture checks.
- **Not a cryptographic guarantee**: the harness raises the cost and complexity of IPI attacks; it does not eliminate them. It is best viewed as a defense-in-depth layer rather than a silver bullet.

---

## 4. High-Level Results

The experiments compare four defenses on the same set of stress-valid (attack-pressure-confirmed) AgentDojo task-injection pairs:

- **No defense** baseline.
- **Spotlighting with delimiting** (a prompt-level baseline).
- **Transformer-based PI detector** (a learned input classifier).
- **The biomimetic harness** described above.

Qualitative findings, observed across multiple LLM backends:

- The no-defense baseline remains vulnerable across suites; the prompt-level baseline and the learned detector reduce attacks but leave clear gaps, especially when the injection uses the same tools as the benign task or when the payload is rewritten in a style the classifier has not seen.
- The biomimetic harness consistently drives the attack success rate toward zero on stress-valid batches while retaining competitive benign utility. On one backend it achieves near-perfect security with only modest utility loss; on another, weaker backend the security remains near-perfect but the utility trade-off is larger—highlighting the victim-model dependence mentioned above.
- The learned detector sometimes over-blocks, producing low utility despite reasonable security, which suggests that per-message classification is too coarse for multi-step agent tasks.
- The workspace and travel suites remain the hardest for all defenses, because injections can be embedded in long documents or tool outputs that are semantically close to legitimate content.

These results indicate that a **structural, provenance-aware harness** can be a more robust defense layer than either pure prompt engineering or standalone input classification, particularly for multi-step agent workflows.

---

## 5. Personal Contribution

This project was carried out from problem formulation through implementation, evaluation, and analysis. My specific contributions include:

1. **Problem framing and architecture design**: I proposed treating agent safety as a **pipeline-level** problem rather than a single-model decision, drawing on the biological analogy of folded/gated/cleaved quality control to organize the system into four coarse stages.

2. **End-to-end implementation**: I implemented the harness core (fold/gate/cleave/provenance tracking), the benchmark driver, the gated rerun orchestrator, the configuration layer, and the visualization suite in Python.

3. **Experimental methodology**: I designed the stress-gate procedure to ensure that defense comparisons are only made on batches where the no-defense baseline is actually under attack. I also set up cross-model validation to test generalization across different LLM backends.

4. **Evaluation and debugging**: I ran the full 24-batch AgentDojo seed suite on multiple models, identified and re-ran anomalous batches, diagnosed failure mechanisms (e.g., utility-retention failures on weaker models, stress-invalid batches on low-pressure attacks), and generated comparative figures.

5. **Risk-aware communication**: I documented the trade-offs (utility vs. security, victim-model dependence, fail-closed limitations) rather than reporting only the most favorable numbers.

---

## 6. Why This Matters for AI Safety

As LLM agents move from demos to production, the attack surface shifts from the model itself to the **agent execution loop**: the way inputs are parsed, plans are formed, tools are called, and outputs are written back. A defense that only hardens the model's system prompt will not be enough. This project contributes a **reusable engineering framework** for building structural, fail-closed harnesses around LLM agents, with transparent evaluation against public benchmarks. The code, configs, and evaluation pipeline are designed so that future attacks and future defenses can be plugged in without rewriting the harness from scratch.

---

*Note: This brief intentionally describes the system at the architectural level and reports qualitative conclusions. Exact algorithmic mechanisms, scoring functions, and quantitative tables are reserved for the ongoing technical paper.*
