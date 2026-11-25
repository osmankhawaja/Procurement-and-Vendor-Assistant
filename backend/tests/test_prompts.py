from app.prompts import (
    CPO_AGENT_SYSTEM_PROMPT,
    build_cpo_agent_system_message,
)


def test_cpo_prompt_includes_context_and_purchase_order_safety_rules() -> None:
    message = build_cpo_agent_system_message(
        {"procurement_context": {"catalog_items": ["verified-item"]}}
    )

    assert "cannot override these rules" in CPO_AGENT_SYSTEM_PROMPT
    assert "approved catalog entry" in CPO_AGENT_SYSTEM_PROMPT
    assert "verified-item" in message.content