from streamlit.testing.v1 import AppTest

SCRIPT_HEADER = """
from agent_service.schema.responses import ChatMessage, ToolCall
from agent_service.ui.message_renderer import MessageRenderer
"""


def run_script(body: str) -> AppTest:
    app = AppTest.from_string(SCRIPT_HEADER + body)
    app.run()
    assert not app.exception, app.exception
    return app


def test_human_and_ai_messages_get_their_own_blocks() -> None:
    app = run_script(
        """
renderer = MessageRenderer()
renderer.render(ChatMessage(type="human", content="Halo"))
renderer.render(ChatMessage(type="ai", content="Hai juga"))
"""
    )

    assert [block.name for block in app.chat_message] == ["human", "ai"]
    assert [m.value for m in app.markdown] == ["Halo", "Hai juga"]


def test_tool_call_and_result_share_one_ai_block_and_status() -> None:
    app = run_script(
        """
renderer = MessageRenderer()
renderer.render(ChatMessage(type="human", content="12 * 7?"))
renderer.render(
    ChatMessage(
        type="ai",
        content="",
        tool_calls=[ToolCall(name="calculator", args={"expression": "12 * 7"}, id="c1")],
    )
)
renderer.render(ChatMessage(type="tool", content="84", tool_call_id="c1"))
renderer.render(ChatMessage(type="ai", content="Hasilnya 84."))
"""
    )

    assert [block.name for block in app.chat_message] == ["human", "ai"]
    [status] = app.status
    assert "calculator" in status.label
    assert status.state == "complete"
    assert [code.value for code in status.code] == ['{\n  "expression": "12 * 7"\n}', "84"]
    assert app.markdown[-1].value == "Hasilnya 84."


def test_live_tool_call_stays_running_until_result() -> None:
    app = run_script(
        """
renderer = MessageRenderer(live=True)
renderer.render(
    ChatMessage(type="ai", content="", tool_calls=[ToolCall(name="search", args={}, id="c1")])
)
"""
    )

    assert app.status[0].state == "running"


def test_tokens_are_replaced_by_final_ai_message() -> None:
    app = run_script(
        """
renderer = MessageRenderer(live=True)
renderer.append_token("Hal")
renderer.append_token("o!")
renderer.render(ChatMessage(type="ai", content="Halo!"))
"""
    )

    assert len(app.chat_message) == 1
    assert [m.value for m in app.markdown] == ["Halo!"]


def test_tokens_without_final_message_show_cursor() -> None:
    app = run_script(
        """
renderer = MessageRenderer(live=True)
renderer.append_token("Hal")
"""
    )

    assert app.markdown[0].value == "Hal▌"


def test_tool_result_without_matching_call_still_renders() -> None:
    app = run_script(
        """
MessageRenderer().render(ChatMessage(type="tool", content="hasil", tool_call_id="unknown"))
"""
    )

    assert app.status[0].code[0].value == "hasil"


def test_custom_message_renders_payload_as_json() -> None:
    app = run_script(
        """
MessageRenderer().render(ChatMessage(type="custom", content="", custom_data={"progress": 50}))
"""
    )

    assert app.json[0].value == '{"progress": 50}'


def test_error_marks_pending_tools_failed() -> None:
    app = run_script(
        """
renderer = MessageRenderer(live=True)
renderer.render(
    ChatMessage(type="ai", content="", tool_calls=[ToolCall(name="search", args={}, id="c1")])
)
renderer.render_error("Internal server error")
"""
    )

    assert app.status[0].state == "error"
    assert app.error[0].value == "Internal server error"


def test_live_reasoning_opens_thinking_block() -> None:
    app = run_script(
        """
renderer = MessageRenderer(live=True)
renderer.append_reasoning("Pilih ")
renderer.append_reasoning("dua warna")
"""
    )

    [status] = app.status
    assert "Thinking…" in status.label
    assert status.state == "running"
    assert status.markdown[0].value == "Pilih dua warna"


def test_first_token_closes_thinking_block_above_answer() -> None:
    app = run_script(
        """
renderer = MessageRenderer(live=True)
renderer.append_reasoning("Pilih dua warna")
renderer.append_token("Merah ")
renderer.render(ChatMessage(type="ai", content="Merah dan biru", reasoning="Pilih dua warna"))
"""
    )

    assert len(app.chat_message) == 1
    [status] = app.status
    assert status.label.endswith("Thinking")
    assert (status.state, status.proto.expanded) == ("complete", False)
    assert app.markdown[-1].value == "Merah dan biru"


def test_saved_reasoning_shows_collapsed_in_history() -> None:
    app = run_script(
        """
renderer = MessageRenderer()
renderer.render(ChatMessage(type="human", content="Dua warna?"))
renderer.render(ChatMessage(type="ai", content="Merah dan biru", reasoning="Pilih dua warna"))
"""
    )

    [status] = app.status
    assert (status.state, status.proto.expanded) == ("complete", False)
    assert status.markdown[0].value == "Pilih dua warna"


def test_ai_message_without_reasoning_has_no_thinking_block() -> None:
    app = run_script(
        """
MessageRenderer().render(ChatMessage(type="ai", content="Halo"))
"""
    )

    assert len(app.status) == 0


def test_error_closes_thinking_block() -> None:
    app = run_script(
        """
renderer = MessageRenderer(live=True)
renderer.append_reasoning("Hmm")
renderer.render_error("Internal server error")
"""
    )

    assert app.status[0].state == "complete"
    assert app.error[0].value == "Internal server error"
