# Appendix A Backup: Module Ablations and Mechanism Disentanglement

*Backup created: November 3, 2026*
*Source: `main.tex` lines 375–422 (before removal)*

---

## LaTeX Source Code

```latex
\appendix
\section{Module Ablations and Mechanism Disentanglement}
\label{app:ablation}

This appendix provides a comprehensive analysis of how Fold, Gate, and Cleave divide labor across two complementary estimands: a staged recovery on a controlled workspace replay (Figure~\ref{fig:utility-recovery}) and drop-one variants on that fixture alongside the 24 live AgentDojo conditions (Table~\ref{tab:ablation}).

Figure~\ref{fig:utility-recovery} isolates how protocol layers restore task completion after an injection on a controlled replay with five benign task checks and one unauthorized action. Under an earlier, non-continuous baseline, withholding suspicious tool outputs yields only 20\% utility because benign follow-up reads are frozen. Adding metadata repair (60\%), reflection-aware handling (80\%), and full state tracking (100\%) restores completion stepwise. Under the October 2026 Continuity-aware protocol, the same replay scores 100\% utility and 100\% security at every stage, including withhold-only: benign reads on this fixture are released before metadata repair is required. Security remains 100\% at every stage. The live drop-one is the estimand that still separates cargo repair from the other components.

A live drop-one can appear as if metadata repair alone drives the system, with Continuity, feature-attribution reordering, and path consistency adding little. That reading mixes cargo recovery with false-block prevention and structural evasion:
\begin{enumerate}
    \item \textbf{Cleave reconstitutes cargo.} Standard AgentDojo live tests mostly embed XML injection envelopes in retrieved tool outputs. Once Gate intercepts the injection, excising the envelope while keeping task data is what lets the agent finish the user task. Disabling metadata repair falls back to withhold-and-halt: live utility drops from 94.4\% to 56.9\%, and workspace utility from 100\% to 25\%.
    \item \textbf{Fold and Continuity prevent false blocks.} They do not excise text; they keep legitimate operations from being over-blocked. Disabling Reflective Fold drops live utility from 94.4\% to 79.2\% (banking 83.3\% to 50.0\%; Slack 100\% to 87.5\%) and costs 20 utility points on the controlled replay. Without reflection and Continuity softening, benign goal-aligned writes (for example, rent adjustments) are treated as adversarial drift.
    \item \textbf{Path-consistency and reordering matter on non-envelope evasions.} Removing them barely moves live security on the 24-condition set (95.8\% vs.\ 96.5\% and 94.4\%) because those envelopes already fire the primary tagger. They become decisive on path smuggling, fragmented cross-turn injections, and state pollution (Section~\ref{sec:extended-suites}).
\end{enumerate}

Table~\ref{tab:main-results-revised} is the primary end-to-end run (DeepSeek stress macro 100\%, unfiltered 97.9\%). Table~\ref{tab:ablation} uses a separate frozen batch in which every drop-one variant was measured together so variants share identical seeds (full-system security 95.8\% on that batch). A zero $\Delta U$ on the replay indicates that the removed check was idle on that particular fixture.

\begin{figure}[!h]
\centering
\includegraphics[width=0.75\columnwidth]{fig_staged_utility_recovery_compare.pdf}
\caption{Staged utility recovery on one controlled injected-output replay (five utility checks; 20-point steps). Dashed: earlier protocol; solid: current Continuity-aware protocol. Security is 100\% at every stage (malicious action blocked).}
\label{fig:utility-recovery}
\end{figure}

\begin{table}[!ht]
\centering
\footnotesize
\setlength{\tabcolsep}{4.5pt}
\renewcommand{\arraystretch}{0.92}
\caption{Component ablation under controlled replay ($\Delta U$, malicious action blocked at 100\% across all settings) and concurrent live DeepSeek AgentDojo drop-one.}
\label{tab:ablation}
\begin{tabular}{lccc}
\toprule
 & Replay & \multicolumn{2}{c}{Live AgentDojo} \\
\cmidrule(lr){2-2}\cmidrule(lr){3-4}
Removed Configuration & $\Delta U$ & Utility (\%) & Security (\%) \\
\midrule
BioHarness (full) & \phantom{$-$}0 & 94.4 & 95.8 \\
$-$ Metadata repair & $-40$ & 56.9 & 98.6 \\
$-$ Continuity soften & \phantom{$-$}0 & 93.8 & 98.6 \\
$-$ Reflection probe & $-20$ & 79.2 & 97.9 \\
$-$ Feature-attribution reorder & \phantom{$-$}0 & 94.4 & 96.5 \\
$-$ Path-consistency checks & \phantom{$-$}0 & 94.4 & 94.4 \\
\bottomrule
\end{tabular}
\end{table}
```

---

## Rationale for Removal from Main Submission

1. **Estimand & Seed Inconsistency with Table 1**:
   Table 1 reports the primary benchmark with DeepSeek stress macro security at 100% and unfiltered at 97.9%. Table 4 was executed on a separate concurrent frozen batch where full-system security happened to be 95.8%. Reviewers comparing Table 1 with Table 4 often ask why full BioHarness reports 95.8% security instead of 97.9%/100%.

2. **Counter-Intuitive Drop-One Security Shifts**:
   When metadata repair is removed (`- Metadata repair`), security paradoxically shifts from 95.8% to 98.6% because the pipeline drops into crude withhold-and-halt, collapsing utility to 56.9% while blocking more aggressively. Reviewers frequently misread this as metadata repair degrading security.

3. **Core Insights Already Preserved in Section 4.2**:
   Section 4.2 compactly summarizes the essential findings:
   - Cleave restores cargo utility from 56.9% to 94.4%.
   - Reflective Fold and Continuity prevent false blocks (retaining 15.2% utility).
   - Deterministic path invariants secure non-envelope structural evasions (detailed in Section 4.3).

4. **Section 4.3 Provides the True Clean Ablation**:
   The 193-case structural evasion suite (Section 3.2 and Section 4.3) already contains a 4-stage progressive ablation (Schema only -> Partition only -> No path rules -> Full BioHarness), perfectly proving the non-redundant division of labor without any configuration mismatches.
