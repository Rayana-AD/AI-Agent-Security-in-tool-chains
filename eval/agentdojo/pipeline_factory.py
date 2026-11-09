"""Build AgentDojo pipelines for paper baselines + BioHarness defenses."""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import partial
from typing import Literal
from urllib.parse import urlparse

import openai
from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, DEFENSES, load_system_message
from agentdojo.agent_pipeline.basic_elements import InitQuery, SystemMessage
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop, ToolsExecutor, tool_result_to_str

from eval.agentdojo.bio_harness_guard import (
    BioHarnessEpisodeReset,
    BioHarnessPreToolGuard,
    BioHarnessToolGuard,
)
from eval.agentdojo.compatible_llm import CompatibleOpenAILLM, CompatibleOpenAILLMToolFilter

# tool_knowledge attack needs a MODEL_NAMES key inside pipeline.name
AGENTDOJO_PREFIX_BY_PROVIDER = {
    "openai_flagship": "gpt-4o-2024-05-13",
    "openrouter": "gpt-4o-2024-05-13",
    "openrouter_llama70": "gpt-4o-2024-05-13",
    "openai": "gpt-4o-mini-2024-07-18",
    "deepseek": "gpt-4o-mini-2024-07-18",
    "hf": "gpt-4o-mini-2024-07-18",
    "huggingface": "gpt-4o-mini-2024-07-18",
    "gpt4o": "gpt-4o-2024-05-13",
}

BIO_DEFENSES = {
    "bio_04": "idea1_provenance_mlp_bio_04",
    # Legacy remeasure labels (prefer bio_remeasure for new Table 1 runs)
    "bio_05": "idea1_provenance_mlp_bio_04",
    "bio_remeasure": "idea1_provenance_mlp_bio_remeasure",
    # Current-protocol appendix labels. The first five retain historical
    # config keys for compatibility, but all are aligned to bio_remeasure.
    "bio_remeasure_minus_reflection": "bio_04_minus_reflection",
    "bio_remeasure_minus_feature_shuffle": "bio_04_minus_feature_shuffle",
    "bio_remeasure_minus_path_rules": "bio_04_minus_hard_rules",
    "bio_remeasure_minus_continuity": "bio_04_minus_goal_continuity",
    "bio_remeasure_minus_cleave": "bio_04_minus_metadata_repair",
    "bio_remeasure_minus_gate": "bio_remeasure_minus_gate",
    "bio_remeasure_minus_carry": "bio_remeasure_minus_carry",
    "bio_04_minus_reflection": "bio_04_minus_reflection",
    "bio_04_minus_feature_shuffle": "bio_04_minus_feature_shuffle",
    "bio_04_minus_hard_rules": "bio_04_minus_hard_rules",
    "bio_04_minus_goal_continuity": "bio_04_minus_goal_continuity",
    "bio_04_minus_metadata_repair": "bio_04_minus_metadata_repair",
    "bio_idea1": "idea1_only",
    "bio_idea1_provenance": "idea1_provenance",
    "bio_idea1_provenance_mlp": "idea1_provenance_mlp",
    "bio_idea1_provenance_reflection": "idea1_provenance_mlp_reflection",
    "bio_idea1_provenance_reflection_ipi_escalate": "idea1_provenance_mlp_reflection_ipi_escalate",
    "bio_idea1_provenance_reflection_ipi_metadata": "idea1_provenance_mlp_reflection_ipi_metadata",
    "bio_idea1_provenance_reflection_ipi_guided": "idea1_provenance_mlp_reflection_ipi_guided",
    "bio_idea1_provenance_reflection_meta_watch": "idea1_provenance_mlp_refl_meta_watch",
    "bio_idea1_provenance_reflection_meta_light": "idea1_provenance_mlp_refl_meta_light",
    "bio_idea1_provenance_reflection_meta_unified": "idea1_provenance_mlp_refl_meta_unified",
    "bio_idea1_provenance_reflection_meta_full": "idea1_provenance_mlp_refl_meta_full",
    "bio_idea2": "idea2_only",
    "bio_idea2_v2": "idea2_agentdojo",
    "bio_full": "full",
}

PAPER_DEFENSES = [
    "none",
    "tool_filter",
    "spotlighting_with_delimiting",
    "repeat_user_prompt",
    "transformers_pi_detector",
]

_PROVIDER_KEYS = {
    "hf": "huggingface_api_key",
    "huggingface": "huggingface_api_key",
    "hf_llama": "huggingface_api_key",
    "deepseek": "deepseek_api_key",
    "openai": "openai_api_key",
    "openai_flagship": "openai_api_key",
    "openrouter": "openrouter_api_key",
    "openrouter_llama70": "openrouter_api_key",
    "gpt4o": "openai_api_key",
}


def _get_provider_cfg(provider: str) -> dict:
    from bio_harness.config import load_yaml

    root = load_yaml("model.yaml")
    if provider in ("hf", "huggingface", "hf_llama"):
        return dict(root.get("huggingface") or {}) if provider != "hf_llama" else dict(
            (root.get("providers") or {}).get("hf_llama") or root.get("huggingface") or {}
        )
    return dict((root.get("providers") or {}).get(provider) or {})


def _api_key_for(provider: str, settings: dict) -> str:
    env_map = {
        "hf": "HF_TOKEN",
        "huggingface": "HF_TOKEN",
        "hf_llama": "HF_TOKEN",
        "deepseek": "DEEPSEEK_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openai_flagship": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "openrouter_llama70": "OPENROUTER_API_KEY",
        "gpt4o": "OPENAI_API_KEY",
    }
    secret_key = _PROVIDER_KEYS.get(provider, "")
    key = settings.get(secret_key) if provider not in ("hf", "huggingface", "hf_llama") else None
    if provider in ("hf", "huggingface", "hf_llama"):
        key = settings.get("api_key")
    if not key:
        key = os.environ.get(env_map.get(provider, ""), "")
    return str(key or "").strip()


def _validate_provider_endpoint(provider: str, base_url: str) -> None:
    """Fail closed before any paid call if a provider is routed to the wrong API."""
    host = (urlparse(base_url).hostname or "").lower()
    if provider == "deepseek" and host != "api.deepseek.com":
        raise RuntimeError(
            f"DeepSeek mode must use api.deepseek.com, got {host or base_url!r}"
        )
    if (provider == "openrouter" or provider.startswith("openrouter_")) and host != "openrouter.ai":
        raise RuntimeError(
            f"OpenRouter mode must use openrouter.ai, got {host or base_url!r}"
        )


def _ping_api(client: openai.OpenAI, model: str) -> bool:
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply OK"}],
            max_tokens=4,
            temperature=0.0,
        )
        return bool(r.choices[0].message.content)
    except Exception:
        return False


def resolve_llm(
    model_mode: str,
    model_id: str | None = None,
    *,
    model_priority: list[str] | None = None,
) -> tuple[BasePipelineElement, str, str]:
    """Return (llm, display_name, provider_used)."""
    if model_mode == "auto":
        priority = model_priority or ["deepseek", "openai_flagship", "openai", "hf"]
        errors: list[str] = []
        for provider in priority:
            try:
                return resolve_llm(provider, model_id)
            except Exception as e:
                errors.append(f"{provider}: {e}")
        raise RuntimeError("No LLM provider available.\n" + "\n".join(errors))

    if model_mode == "local":
        from bio_harness.config import get_model_settings
        from bio_harness.llm.qwen_backend import QwenBackend
        from eval.agentdojo.inprocess_llm import InProcessQwenLLM

        settings = get_model_settings()
        backend = QwenBackend(
            model_path=settings.get("path"),
            temperature=float(settings.get("temperature", 0.0)),
            max_new_tokens=min(int(settings.get("max_new_tokens", 512)), 256),
        )
        llm = InProcessQwenLLM(backend)
        return llm, llm.name, "local"

    from bio_harness.config import get_model_settings

    settings = get_model_settings()
    pcfg = _get_provider_cfg(model_mode)
    api_key = _api_key_for(model_mode, settings)
    if not api_key:
        label = _PROVIDER_KEYS.get(model_mode, model_mode)
        raise RuntimeError(f"Missing {label} in configs/secrets.yaml or env")

    base_url = pcfg.get("base_url", "https://api.openai.com/v1")
    _validate_provider_endpoint(model_mode, base_url)
    model = model_id or pcfg.get("api_model") or settings.get("api_model") or "gpt-4o-mini"
    default_headers: dict[str, str] = {}
    if model_mode == "openrouter" or model_mode.startswith("openrouter_"):
        default_headers = {
            "HTTP-Referer": "https://github.com/AI-Safety",
            "X-Title": "BioHarness AgentDojo",
        }
    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        timeout=180.0,
        default_headers=default_headers or None,
    )
    if not _ping_api(client, model):
        raise RuntimeError(f"Provider {model_mode} ping failed for model {model}")

    display = f"{model_mode}-{model.split('/')[-1] if '/' in model else model}"
    llm = CompatibleOpenAILLM(client, model, display_name=display, temperature=0.0)
    return llm, display, model_mode


def agentdojo_name_prefix(provider: str) -> str:
    return AGENTDOJO_PREFIX_BY_PROVIDER.get(provider, "gpt-4o-mini-2024-07-18")


def _finalize_pipeline_name(
    pipeline: AgentPipeline, defense_label: str, llm_name: str, provider: str = "hf"
) -> AgentPipeline:
    prefix = agentdojo_name_prefix(provider)
    pipeline.name = f"{prefix}-{defense_label}-{llm_name}"
    return pipeline


def build_pipeline(
    defense: str,
    llm: BasePipelineElement,
    llm_name: str,
    *,
    provider: str = "hf",
    system_message_name: str | None = None,
    tool_output_format: Literal["yaml", "json"] | None = None,
) -> AgentPipeline:
    if defense in BIO_DEFENSES:
        return _build_bio_pipeline(
            BIO_DEFENSES[defense], llm, llm_name, provider, system_message_name, tool_output_format
        )
    if defense == "none" or defense is None:
        return _from_agentdojo_defense(None, llm, llm_name, provider, system_message_name, tool_output_format)
    if defense in {"spotlighting_with_delimiting", "spotlighting"}:
        defense = next((name for name in ("spotlighting", "spotlighting_with_delimiting") if name in DEFENSES), defense)
    if defense not in DEFENSES:
        raise ValueError(f"Unknown defense: {defense}. Choose from {PAPER_DEFENSES + list(BIO_DEFENSES)}")
    if defense == "tool_filter" and not isinstance(llm, (OpenAILLM, CompatibleOpenAILLM)):
        raise ValueError("tool_filter requires OpenAI-compatible LLM")
    if defense == "tool_filter" and isinstance(llm, CompatibleOpenAILLM):
        return _build_tool_filter_pipeline(
            llm, llm_name, provider, system_message_name, tool_output_format
        )
    return _from_agentdojo_defense(defense, llm, llm_name, provider, system_message_name, tool_output_format)


def _build_bio_pipeline(
    config_key: str,
    llm: BasePipelineElement,
    llm_name: str,
    provider: str,
    system_message_name: str | None,
    tool_output_format: Literal["yaml", "json"] | None,
) -> AgentPipeline:
    system_message = load_system_message(system_message_name)
    if tool_output_format == "json":
        import json

        formatter: Callable = partial(tool_result_to_str, dump_fn=json.dumps)
    else:
        formatter = tool_result_to_str

    guard = BioHarnessToolGuard(
        config_key,
        raise_on_block=False,
        schema_fold_tool_outputs=False,
        agentdojo_idea2=(config_key == "idea2_agentdojo"),
    )
    pre_guard = BioHarnessPreToolGuard(config_key, raise_on_block=False)
    tools_loop = ToolsExecutionLoop([pre_guard, ToolsExecutor(formatter), guard, llm])
    pipeline = AgentPipeline(
        [SystemMessage(system_message), InitQuery(), BioHarnessEpisodeReset(), llm, tools_loop]
    )
    return _finalize_pipeline_name(pipeline, config_key, llm_name, provider)


def _build_tool_filter_pipeline(
    llm: CompatibleOpenAILLM,
    llm_name: str,
    provider: str,
    system_message_name: str | None,
    tool_output_format: Literal["yaml", "json"] | None,
) -> AgentPipeline:
    from agentdojo.agent_pipeline.agent_pipeline import TOOL_FILTER_PROMPT

    system_message = load_system_message(system_message_name)
    if tool_output_format == "json":
        import json

        formatter: Callable = partial(tool_result_to_str, dump_fn=json.dumps)
    else:
        formatter = tool_result_to_str

    tools_loop = ToolsExecutionLoop([ToolsExecutor(formatter), llm])
    pipeline = AgentPipeline(
        [
            SystemMessage(system_message),
            InitQuery(),
            CompatibleOpenAILLMToolFilter(TOOL_FILTER_PROMPT, llm.client, llm.model),
            llm,
            tools_loop,
        ]
    )
    return _finalize_pipeline_name(pipeline, "tool_filter", llm_name, provider)


def _from_agentdojo_defense(
    defense: str | None,
    llm: BasePipelineElement,
    llm_name: str,
    provider: str,
    system_message_name: str | None,
    tool_output_format: Literal["yaml", "json"] | None,
) -> AgentPipeline:
    from agentdojo.agent_pipeline.agent_pipeline import PipelineConfig

    cfg = PipelineConfig(
        llm=llm,
        model_id=None,
        defense=defense,
        system_message_name=system_message_name,
        system_message=None,
        tool_output_format=tool_output_format,
    )
    pipeline = AgentPipeline.from_config(cfg)
    return _finalize_pipeline_name(pipeline, defense or "none", llm_name, provider)
