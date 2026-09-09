import pytest

from doppelhand import executor as executor_module
from doppelhand.agent import HALT_TEXT, Agent, _prune_screenshots
from doppelhand.errors import Aborted, Refused, StepLimit
from doppelhand.executor import Executor
from fakes import FakeClient, FakeKeyboard, FakeScreen, response, text_block, tool_block


@pytest.fixture(autouse=True)
def no_settle(monkeypatch):
    monkeypatch.setattr(executor_module, "SETTLE_SECONDS", 0)


def build(responses, keyboard=None):
    keyboard = keyboard or FakeKeyboard()
    executor = Executor(max_edge=1280, screen=FakeScreen(), keyboard=keyboard)
    client = FakeClient(responses)
    return Agent(client=client, executor=executor, max_steps=5), client, keyboard


def image_result(message):
    return [b for b in message["content"] if b.get("type") == "tool_result"]


def test_a_plain_answer_ends_the_run():
    agent, client, _ = build([response([text_block("done")])])
    assert agent.run("say done") == "done"
    assert len(client.requests) == 1


def test_the_toolset_is_declared_and_the_screen_size_is_in_the_prompt():
    agent, client, _ = build([response([text_block("ok")])])
    agent.run("anything")
    request = client.requests[0]
    assert request["tools"] == [{"type": "computer_toolset_20260801"}]
    assert "1280 wide by 720 high" in request["system"]


def test_a_tool_call_is_executed_and_answered():
    agent, client, keyboard = build([
        response([tool_block("left_click", {"coordinate": [10, 20]})], stop_reason="tool_use"),
        response([text_block("clicked")]),
    ])
    assert agent.run("click something") == "clicked"
    assert ("click", "left", 1) in keyboard.calls

    results = image_result(client.requests[1]["messages"][-1])
    assert results[0]["tool_use_id"] == "toolu_1"
    assert results[0]["toolset_name"] == "computer"
    assert results[0]["content"] == [{"type": "text", "text": "OK"}]


def test_a_failed_action_stops_the_rest_of_the_batch():
    calls = [
        tool_block("left_click_drag", {}, block_id="a"),
        tool_block("screenshot", {}, block_id="b"),
    ]
    agent, client, _ = build([
        response(calls, stop_reason="tool_use"),
        response([text_block("recovered")]),
    ])
    agent.run("drag then look")

    first, second = image_result(client.requests[1]["messages"][-1])
    assert first["is_error"] and "start_coordinate" in first["content"]
    assert second["is_error"] and second["content"] == HALT_TEXT


def test_a_screenshot_comes_back_as_an_image():
    agent, client, _ = build([
        response([tool_block("screenshot")], stop_reason="tool_use"),
        response([text_block("looked")]),
    ])
    agent.run("look")
    result = image_result(client.requests[1]["messages"][-1])[0]
    assert result["content"][0]["type"] == "image"


def test_only_the_newest_tool_result_carries_the_cache_breakpoint():
    agent, client, _ = build([
        response([tool_block("screenshot", block_id="a")], stop_reason="tool_use"),
        response([tool_block("screenshot", block_id="b")], stop_reason="tool_use"),
        response([text_block("done")]),
    ])
    agent.run("look twice")
    marked = [block for message in agent.messages
              if isinstance(message.get("content"), list)
              for block in message["content"]
              if isinstance(block, dict) and "cache_control" in block]
    assert len(marked) == 1
    assert marked[0]["tool_use_id"] == "b"


def test_holding_escape_aborts_the_run():
    keyboard = FakeKeyboard()
    keyboard.abort = True
    agent, _, _ = build([response([tool_block("left_click")], stop_reason="tool_use")],
                        keyboard=keyboard)
    with pytest.raises(Aborted):
        agent.run("click")


def test_a_refusal_is_raised_rather_than_looped_over():
    from types import SimpleNamespace

    details = SimpleNamespace(category="cyber", explanation="no")
    agent, _, _ = build([response([], stop_reason="refusal", stop_details=details)])
    with pytest.raises(Refused) as caught:
        agent.run("do something dubious")
    assert caught.value.category == "cyber"


def test_the_step_budget_is_enforced():
    turns = [response([tool_block("screenshot")], stop_reason="tool_use") for _ in range(5)]
    agent, _, _ = build(turns)
    with pytest.raises(StepLimit):
        agent.run("loop forever")


def test_old_screenshots_are_pruned_in_batches():
    def message(n):
        return {"role": "user", "content": [{
            "type": "tool_result", "tool_use_id": str(n),
            "content": [{"type": "image", "source": {"data": "x"}}],
        }]}

    messages = [message(n) for n in range(4)]
    assert _prune_screenshots(messages, keep=2, batch=2) == 0

    messages = [message(n) for n in range(6)]
    assert _prune_screenshots(messages, keep=2, batch=2) == 4
    surviving = [m["content"][0]["tool_use_id"] for m in messages
                 if m["content"][0]["content"][0]["type"] == "image"]
    assert surviving == ["4", "5"]
