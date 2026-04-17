from src.services.task_contract import (
    build_policy_flags,
    build_task_context,
    get_market_id,
    get_policy_flags,
    get_scenario_type,
    is_cache_allowed,
    should_delete_after_process,
)


def test_build_task_context_preserves_domain_metadata():
    ctx = build_task_context(
        {
            "style": "passport",
            "profession": "designer",
        },
        market_id="ru",
        service_role="api",
        compute_mode="remote",
        scenario_slug="document-photo",
        scenario_type="standalone",
        entry_mode="landing",
        trace_id="trace-123",
        policy_flags=build_policy_flags(
            cache_allowed=False,
            delete_after_process=True,
            retention_policy="ephemeral",
            data_class="regional_photo",
        ),
        artifact_refs={"market_input_path": "inputs/u/t.jpg"},
    )

    assert ctx["style"] == "passport"
    assert ctx["profession"] == "designer"
    assert ctx["market_id"] == "ru"
    assert ctx["service_role"] == "api"
    assert ctx["compute_mode"] == "remote"
    assert ctx["scenario_slug"] == "document-photo"
    assert ctx["entry_mode"] == "landing"
    assert ctx["trace_id"] == "trace-123"
    assert get_scenario_type(ctx) == "standalone"
    assert ctx["artifact_refs"]["market_input_path"] == "inputs/u/t.jpg"


def test_policy_helpers_reflect_cache_and_cleanup_rules():
    ctx = {
        "market_id": "ru",
        "policy_flags": {
            "cache_allowed": False,
            "delete_after_process": True,
            "retention_policy": "ephemeral",
            "data_class": "regional_photo",
        },
    }

    assert get_market_id(ctx) == "ru"
    assert get_policy_flags(ctx)["retention_policy"] == "ephemeral"
    assert is_cache_allowed(ctx) is False
    assert should_delete_after_process(ctx) is True
