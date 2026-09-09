"""The perceive-decide-act loop: Claude looks at the screen and doppelhand acts."""

from __future__ import annotations

from collections.abc import Callable

from doppelhand.errors import ActionError, Aborted, Refused, StepLimit
from doppelhand.executor import Executor

DEFAULT_MODEL = "claude-opus-5"
TOOLSET_NAME = "computer"
COMPUTER_TOOLSET = {"type": "computer_toolset_20260801"}
HALT_TEXT = "Not executed: an earlier computer action in this turn failed."

SYSTEM_PROMPT = (
    "You are operating a Windows desktop through screenshots and synthetic mouse and "
    "keyboard input. Screen coordinates are the pixels of the screenshots you receive: "
    "{width} wide by {height} high, origin at the top left.\n"
    "Take a screenshot before your first action and after any action that changes what "
    "is on screen, and read the result before deciding the next step. Prefer keyboard "
    "shortcuts where they are more reliable than clicking.\n"
    "Do only what the task asks. If the task is finished, say so and stop calling tools. "
    "If you are stuck, cannot see what you need, or the screen is not what you expected, "
    "stop and explain what you see instead of guessing."
)


class Agent:
    """Runs one task to completion, or until the step budget is spent."""

    def __init__(
        self,
        client=None,
        model: str = DEFAULT_MODEL,
        executor: Executor | None = None,
        max_steps: int = 30,
        max_tokens: int = 16000,
        max_images: int = 10,
        prune_batch: int = 5,
        on_event: Callable[[str, str], None] | None = None,
    ):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.executor = executor or Executor()
        self.max_steps = max_steps
        self.max_tokens = max_tokens
        self.max_images = max_images
        self.prune_batch = prune_batch
        self.on_event = on_event or (lambda kind, detail: None)
        self.messages: list[dict] = []

    def run(self, task: str) -> str:
        width, height = self.executor.view_size
        self.messages = [{"role": "user", "content": task}]

        for step in range(1, self.max_steps + 1):
            self.on_event("step", f"{step}/{self.max_steps}")
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT.format(width=width, height=height),
                tools=[COMPUTER_TOOLSET],
                messages=self.messages,
            )
            if response.stop_reason == "refusal":
                details = getattr(response, "stop_details", None)
                raise Refused(getattr(details, "category", None),
                              getattr(details, "explanation", None))

            self.messages.append({"role": "assistant", "content": response.content})
            for block in response.content:
                if getattr(block, "type", None) == "text" and block.text.strip():
                    self.on_event("say", block.text.strip())

            calls = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            if not calls:
                return _final_text(response)

            results = self._run_batch(calls)
            _prune_screenshots(self.messages, self.max_images, self.prune_batch)
            _move_cache_breakpoint(self.messages, results)
            self.messages.append({"role": "user", "content": results})

        raise StepLimit(f"stopped after {self.max_steps} steps without finishing")

    def _run_batch(self, calls: list) -> list[dict]:
        """Run the turn's actions in order. After a failure the rest are refused rather
        than run, because each one assumed the screen the failed action would have left."""
        results = []
        halted = False
        for call in calls:
            if halted:
                results.append(_error_result(call.id, HALT_TEXT))
                continue
            if getattr(call, "toolset_name", TOOLSET_NAME) != TOOLSET_NAME:
                results.append(_error_result(call.id, f"unknown tool: {call.name}"))
                halted = True
                continue
            self.on_event("act", f"{call.name} {dict(call.input) if call.input else ''}".strip())
            try:
                content = self.executor.dispatch(call.name, dict(call.input or {}))
            except Aborted:
                raise
            except ActionError as exc:
                results.append(_error_result(call.id, str(exc)))
                halted = True
            else:
                results.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "toolset_name": TOOLSET_NAME,
                    "content": content,
                })
        return results


def _final_text(response) -> str:
    return "\n".join(b.text for b in response.content
                     if getattr(b, "type", None) == "text").strip()


def _error_result(tool_use_id: str, message: str) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "toolset_name": TOOLSET_NAME,
        "is_error": True,
        "content": message,
    }


def _move_cache_breakpoint(messages: list[dict], results: list[dict]) -> None:
    """Keep one cache breakpoint, on the newest tool result. Everything before it is a
    stable prefix that the next request can read from cache instead of resending."""
    for message in messages:
        for block in message.get("content", []) if isinstance(message.get("content"), list) else []:
            if isinstance(block, dict):
                block.pop("cache_control", None)
    if results:
        results[-1]["cache_control"] = {"type": "ephemeral"}


def _prune_screenshots(messages: list[dict], keep: int, batch: int) -> int:
    """Drop all but the newest `keep` screenshots once `batch` extra ones have piled up.

    Pruning rewrites history and so costs a cache read, which is why it waits for a
    batch instead of trimming one image per turn.

    Returns the number of screenshots removed.
    """
    blocks = [block for message in messages
              for block in _image_blocks(message)]
    if len(blocks) <= keep + batch:
        return 0
    removed = 0
    for block in blocks[:len(blocks) - keep]:
        block["content"] = [{"type": "text", "text": "[earlier screenshot removed]"}]
        removed += 1
    return removed


def _image_blocks(message: dict) -> list[dict]:
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content
            if isinstance(block, dict)
            and block.get("type") == "tool_result"
            and any(isinstance(part, dict) and part.get("type") == "image"
                    for part in block.get("content", []))]
