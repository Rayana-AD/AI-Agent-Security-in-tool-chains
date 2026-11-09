"""Unit tests for stress manifest classification."""

from eval.run_stress_manifest import classify_agentdojo, build_seed_profile


def _ep(
    *,
    suite="banking",
    user_task="user_task_0",
    attack="important_instructions_persona",
    injection="injection_task_0",
    defense="none",
    attack_success=True,
    utility=True,
    model_mode="deepseek",
):
    return {
        "suite": suite,
        "user_task": user_task,
        "attack": attack,
        "injection_task": injection,
        "defense": defense,
        "model_mode": model_mode,
        "utility": utility,
        "attack_success": attack_success,
        "defense_success": not attack_success,
        "log_path": f"/tmp/{suite}/{user_task}/{defense}.json",
    }


def test_none_usable_and_spotlight_gap():
    episodes = [
        _ep(defense="none", attack_success=True),
        _ep(defense="spotlighting_with_delimiting", attack_success=True),
        _ep(defense="bio_04", attack_success=False),
        _ep(suite="slack", user_task="user_task_1", defense="none", attack_success=False),
    ]
    out = classify_agentdojo(episodes)
    assert out["n_none_usable"] == 1
    assert out["n_spotlight_gaps"] == 1
    assert out["n_bio_04_wins"] == 1
    assert out["spotlight_gaps"][0]["suite"] == "banking"


def test_stress_valid_batch():
    episodes = [
        _ep(defense="none", attack_success=True),
        _ep(user_task="user_task_1", defense="none", attack_success=False),
    ]
    out = classify_agentdojo(episodes)
    batches = out["batch_summaries"]
    assert len(batches) == 1
    assert batches[0]["none_ASR"] == 0.5
    assert batches[0]["stress_valid"] is True


def test_build_seed_profile_from_gaps():
    manifest = {
        "agentdojo": {
            "spotlight_gaps": [
                {
                    "suite": "banking",
                    "user_task": "user_task_2",
                    "attack": "important_instructions_persona",
                    "injection_task": "injection_task_0",
                }
            ]
        }
    }
    seed = build_seed_profile(manifest)
    assert seed["name"] == "m1_manifest_seed"
    assert seed["suite_quotas"]["banking"] == 1
    assert "important_instructions_persona" in seed["attacks"]
