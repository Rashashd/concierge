from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.cost import TurnCost, extract_turn_cost


def test_sums_tokens_across_multiple_ai_messages() -> None:
    tenant_id = uuid4()
    messages = [
        HumanMessage(content="hi"),
        AIMessage(
            content="calling tool",
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        ),
        HumanMessage(content="tool result"),
        AIMessage(
            content="final answer",
            usage_metadata={"input_tokens": 20, "output_tokens": 8, "total_tokens": 28},
        ),
    ]

    cost = extract_turn_cost(tenant_id, "gpt-4o-mini", messages)

    assert isinstance(cost, TurnCost)
    assert cost.tenant_id == tenant_id
    assert cost.model == "gpt-4o-mini"
    assert cost.prompt_tokens == 30
    assert cost.completion_tokens == 13
    assert cost.total_tokens == 43


def test_returns_zeros_when_no_ai_messages() -> None:
    tenant_id = uuid4()
    messages: list = [HumanMessage(content="hello"), SystemMessage(content="sys")]

    cost = extract_turn_cost(tenant_id, "gpt-4o-mini", messages)

    assert cost.prompt_tokens == 0
    assert cost.completion_tokens == 0
    assert cost.total_tokens == 0


def test_ignores_ai_messages_without_usage_metadata() -> None:
    tenant_id = uuid4()
    messages = [
        AIMessage(content="no metadata here"),
        AIMessage(
            content="with metadata",
            usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
        ),
    ]

    cost = extract_turn_cost(tenant_id, "gpt-4o-mini", messages)

    assert cost.prompt_tokens == 5
    assert cost.completion_tokens == 2
    assert cost.total_tokens == 7


def test_empty_message_list_returns_zeros() -> None:
    cost = extract_turn_cost(uuid4(), "gpt-4o-mini", [])

    assert cost.prompt_tokens == 0
    assert cost.completion_tokens == 0
    assert cost.total_tokens == 0
