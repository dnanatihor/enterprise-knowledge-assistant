"""Scripted rewrite, answer, and escalation policy. Transcripts are retained for tests."""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage, BaseMessage

from knowledge_assistant.platform import register_policy, transcript

TRANSCRIPTS: list[str] = []


def knowledge_policy(messages: list[BaseMessage], _tool_names: list[str]) -> AIMessage:
    text = transcript(messages)
    TRANSCRIPTS.append(text)
    if "TASK: ESCALATE" in text:
        return AIMessage(content="Escalation drafted from the question and confidence only.")
    if "TASK: REWRITE" in text:
        question = text.split("QUESTION:", 1)[-1].strip().splitlines()[0].strip()
        return AIMessage(content=question)
    match = re.search(r"GROUNDED: (.+)", text)
    if match:
        return AIMessage(content=match.group(1).strip())
    return AIMessage(content="I don't know.")


register_policy("knowledge", knowledge_policy)
