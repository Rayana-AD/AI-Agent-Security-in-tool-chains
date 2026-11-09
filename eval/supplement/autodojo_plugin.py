"""AutoDojo defense plugin — register BioHarness + peer defenses via AGENTDOJO_DEFENSE_PLUGINS.

Usage (from repo root):
  export AGENTDOJO_DEFENSE_PLUGINS=eval.supplement.autodojo_plugin
  export PYTHONPATH="$PWD/third_party/AutoDojo/agentdojo/src:$PWD/src:$PWD"
  python -m agentdojo.scripts.benchmark --defense bio_04 ...

MELON and Task Shield cannot use the default plugin slot (filter after
ToolsExecutor). Layouts match the 24-condition peer pipelines:

  melon:        [ToolsExecutor, MelonDefense(llm)]   # MELON calls llm itself
  task_shield:  [TaskShieldDefense(llm), ToolsExecutor, llm]
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentdojo.agent_pipeline.agent_pipeline import PipelineConfig

BIO04_CONFIG_KEY = "idea1_provenance_mlp_bio_04"
BIO_REMEASURE_CONFIG_KEY = "idea1_provenance_mlp_bio_remeasure"
BIO_DEFENSES = {
    "bio_04": BIO04_CONFIG_KEY,
    "bio_05": BIO04_CONFIG_KEY,
    "bio_remeasure": BIO_REMEASURE_CONFIG_KEY,
}
_FROM_CONFIG_PATCHED = False


def _bio04_factory(config: PipelineConfig):
    """Legacy slot; full pipeline is built in ``_bio_pipeline`` via ``from_config`` patch."""
    from eval.agentdojo.bio_harness_guard import BioHarnessToolGuard

    return BioHarnessToolGuard(BIO04_CONFIG_KEY, raise_on_block=False)


def _bio_pipeline(cls, config, orig_from_config):
    """Match eval.agentdojo.pipeline_factory: pre-guard, tool guard, episode carry reset."""
    from agentdojo.agent_pipeline.basic_elements import InitQuery
    from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop
    from eval.agentdojo.bio_harness_guard import (
        BioHarnessEpisodeReset,
        BioHarnessPreToolGuard,
        BioHarnessToolGuard,
    )

    defense = config.defense
    config_key = BIO_DEFENSES[defense]
    config.defense = None
    try:
        pipeline = orig_from_config(cls, config)
    finally:
        config.defense = defense

    loop = next((el for el in pipeline.elements if isinstance(el, ToolsExecutionLoop)), None)
    if loop is None:
        raise RuntimeError(f"{defense} plugin: no ToolsExecutionLoop in vanilla pipeline")
    executor = loop.elements[0]
    llm = loop.elements[-1]
    pre = BioHarnessPreToolGuard(config_key, raise_on_block=False)
    guard = BioHarnessToolGuard(
        config_key,
        raise_on_block=False,
        schema_fold_tool_outputs=False,
    )
    loop.elements = [pre, executor, guard, llm]

    elements = list(pipeline.elements)
    for i, el in enumerate(elements):
        if isinstance(el, InitQuery):
            if not any(getattr(e, "name", "") == "bio-harness-episode-reset" for e in elements):
                elements.insert(i + 1, BioHarnessEpisodeReset())
            break
    pipeline.elements = elements
    prefix = pipeline.name.rsplit("/", 1)[0]
    pipeline.name = f"{prefix}/{defense}"
    return pipeline


def _peer_pipeline(cls, config, orig_from_config):
    from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop
    from eval.agentdojo.peer_defenses import MelonDefense, TaskShieldDefense

    defense = config.defense
    config.defense = None
    try:
        pipeline = orig_from_config(cls, config)
    finally:
        config.defense = defense

    loop = next((el for el in pipeline.elements if isinstance(el, ToolsExecutionLoop)), None)
    if loop is None:
        raise RuntimeError(f"{defense} plugin: no ToolsExecutionLoop in vanilla pipeline")
    executor = loop.elements[0]
    llm = loop.elements[-1]
    if defense == "melon":
        loop.elements = [executor, MelonDefense(llm)]
    elif defense == "task_shield":
        loop.elements = [TaskShieldDefense(llm), executor, llm]
    else:
        raise ValueError(f"unsupported peer defense {defense}")
    prefix = pipeline.name.rsplit("/", 1)[0]
    pipeline.name = f"{prefix}/{defense}"
    return pipeline


def register_all() -> None:
    global _FROM_CONFIG_PATCHED
    from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, DEFENSES, register_defense

    for name in BIO_DEFENSES:
        register_defense(name, _bio04_factory)
    for name in ("melon", "task_shield"):
        if name not in DEFENSES:
            DEFENSES.append(name)

    if _FROM_CONFIG_PATCHED:
        return
    orig = AgentPipeline.from_config.__func__

    def from_config_patched(cls, config):
        defense = getattr(config, "defense", None)
        if defense in BIO_DEFENSES:
            return _bio_pipeline(cls, config, orig)
        if defense in ("melon", "task_shield"):
            return _peer_pipeline(cls, config, orig)
        return orig(cls, config)

    AgentPipeline.from_config = classmethod(from_config_patched)
    _FROM_CONFIG_PATCHED = True


register_all()
