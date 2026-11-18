/**
 * Converter percakapan dengan rekaman SSE asli. Perilaku acuan: `MessageRenderer` Streamlit
 * (FR-20, FR-23, FR-24, FR-29, FR-30).
 */
import type { ThreadMessageLike } from "@assistant-ui/react";
import { describe, expect, it } from "vitest";

import type { ChatMessage, StreamEvent } from "@/api/stream-event";
import {
  appendHuman,
  appendRunEnd,
  applyStreamEvent,
  type ConversationState,
  conversationFromHistory,
  EMPTY_CONVERSATION,
  toThreadMessages,
} from "@/features/chat/conversation";
import { ERROR_SSE, HISTORY_FIXTURES, SSE_FIXTURES } from "@/test/fixtures";

/** Event dari body SSE rekaman, tanpa melewati parser stream. */
function eventsOf(sse: string): StreamEvent[] {
  const events: StreamEvent[] = [];
  for (const line of sse.split("\n")) {
    if (line.startsWith("data: {")) {
      events.push(JSON.parse(line.slice("data: ".length)) as StreamEvent);
    }
  }
  return events;
}

function streamed(prompt: string, sse: string, until?: number): ConversationState {
  let state = appendHuman(EMPTY_CONVERSATION, prompt);
  for (const event of eventsOf(sse).slice(0, until)) {
    state = applyStreamEvent(state, event);
  }
  return state;
}

function historyOf(fixture: { messages: unknown[] }): ConversationState {
  return conversationFromHistory(fixture.messages as ChatMessage[]);
}

type Part = Exclude<ThreadMessageLike["content"], string>[number];

function partsOf(message: ThreadMessageLike | undefined): Part[] {
  if (message === undefined || typeof message.content === "string") {
    return [];
  }
  return [...message.content];
}

/** Ringkasan part yang mudah dibandingkan: tipe, sub-agent, dan nama tool. */
function outline(message: ThreadMessageLike | undefined): string[] {
  return partsOf(message).map((part) => {
    const agent = "parentId" in part && part.parentId ? `@${part.parentId}` : "";
    const tool = part.type === "tool-call" ? `:${part.toolName}` : "";
    return `${part.type}${tool}${agent}`;
  });
}

describe("toThreadMessages", () => {
  it("shows streamed reasoning and tokens live, then the final message (FR-29)", () => {
    const events = eventsOf(SSE_FIXTURES.reasoning);
    const firstToken = events.findIndex((event) => event.type === "token");
    const live = toThreadMessages(streamed("Is 221 prime?", SSE_FIXTURES.reasoning, firstToken + 3), true);

    expect(live.map((message) => message.role)).toEqual(["user", "assistant"]);
    expect(live[1]?.status).toEqual({ type: "running" });
    expect(outline(live[1])).toEqual(["reasoning", "text"]);

    const done = toThreadMessages(streamed("Is 221 prime?", SSE_FIXTURES.reasoning), false);
    const final = events.at(-1) as { content: ChatMessage };
    expect(done[1]?.status).toEqual({ type: "complete", reason: "stop" });
    expect(partsOf(done[1])).toEqual([
      { type: "reasoning", text: final.content.reasoning, parentId: undefined },
      { type: "text", text: final.content.content, parentId: undefined },
    ]);
  });

  it("keeps the streamed reasoning when the final message does not carry it", () => {
    let state = appendHuman(EMPTY_CONVERSATION, "Hi");
    state = applyStreamEvent(state, { type: "reasoning", content: "Thinking it over." });
    state = applyStreamEvent(state, { type: "message", content: { type: "ai", content: "Hello!" } });

    expect(outline(toThreadMessages(state, false)[1])).toEqual(["reasoning", "text"]);
  });

  it("pairs tool results with their call through tool_call_id (FR-20)", () => {
    const messages = toThreadMessages(
      streamed("Compute", SSE_FIXTURES.toolCalls),
      false,
    );

    expect(outline(messages[1])).toEqual(["reasoning", "tool-call:calculator", "reasoning", "text"]);
    const call = partsOf(messages[1]).find((part) => part.type === "tool-call");
    expect(call).toMatchObject({ result: "7006652" });
    expect(call?.type === "tool-call" ? call.args : null).toHaveProperty("expression");
  });

  it("nests sub-agent steps under the expert that made them (FR-23)", () => {
    const messages = toThreadMessages(streamed("Ask", SSE_FIXTURES.subAgents), false);

    expect(messages).toHaveLength(2);
    expect(outline(messages[1])).toEqual([
      "reasoning",
      "tool-call:ask_math_expert",
      "reasoning@math_expert",
      "tool-call:calculator@math_expert",
      "reasoning@math_expert",
      "text@math_expert",
      "reasoning",
      "text",
    ]);
    const expertCall = partsOf(messages[1])[1];
    expect(expertCall?.type === "tool-call" ? String(expertCall.result) : "").toContain("126");
  });

  it("rebuilds the same reply from thread history, reasoning and nesting included", () => {
    for (const [name, sse] of [
      ["subAgents", SSE_FIXTURES.subAgents],
      ["toolCalls", SSE_FIXTURES.toolCalls],
      ["truncated", SSE_FIXTURES.truncated],
    ] as const) {
      const fromHistory = toThreadMessages(historyOf(HISTORY_FIXTURES[name]), false);
      const prompt = (HISTORY_FIXTURES[name].messages[0] as ChatMessage).content;
      const fromStream = toThreadMessages(streamed(prompt, sse), false);

      expect(fromHistory, name).toEqual(fromStream);
    }
  });

  it("marks an answer cut off by the token limit (FR-30)", () => {
    const messages = toThreadMessages(streamed("Essay", SSE_FIXTURES.truncated), false);

    expect(messages[1]?.status).toEqual({ type: "incomplete", reason: "length" });
  });

  it("shows an interrupt question as a plain AI message (FR-24)", () => {
    const messages = toThreadMessages(streamed("Hi", SSE_FIXTURES.interrupt), false);

    expect(partsOf(messages[1])).toEqual([
      { type: "text", text: "What is your birthdate?", parentId: undefined },
    ]);
  });

  it("ends the reply with the error from an error frame", () => {
    const messages = toThreadMessages(streamed("Hi", ERROR_SSE), false);

    expect(messages[1]?.status).toEqual({
      type: "incomplete",
      reason: "error",
      error: "Model provider is unavailable",
    });
  });

  it("starts a new assistant message after every user message", () => {
    let state = streamed("First", SSE_FIXTURES.interrupt);
    state = appendHuman(state, "Second");
    for (const event of eventsOf(SSE_FIXTURES.interrupt)) {
      state = applyStreamEvent(state, event);
    }

    const messages = toThreadMessages(state, false);
    expect(messages.map((message) => [message.role, message.id])).toEqual([
      ["user", "user-0"],
      ["assistant", "assistant-1"],
      ["user", "user-2"],
      ["assistant", "assistant-3"],
    ]);
  });

  it("keeps the assistant message id stable while it streams", () => {
    const events = eventsOf(SSE_FIXTURES.toolCalls);
    const ids = new Set<string | undefined>();
    let state = appendHuman(EMPTY_CONVERSATION, "Compute");
    for (const event of events) {
      state = applyStreamEvent(state, event);
      ids.add(toThreadMessages(state, true)[1]?.id);
    }

    expect([...ids]).toEqual(["assistant-1"]);
  });
});

describe("appendRunEnd", () => {
  it("keeps the streamed text when the user stops the run", () => {
    const events = eventsOf(SSE_FIXTURES.truncated);
    const firstToken = events.findIndex((event) => event.type === "token");
    const stopped = appendRunEnd(streamed("Essay", SSE_FIXTURES.truncated, firstToken + 5), {
      kind: "cancelled",
    });

    const messages = toThreadMessages(stopped, false);
    expect(messages[1]?.status).toEqual({ type: "incomplete", reason: "cancelled" });
    expect(outline(messages[1])).toEqual(["reasoning", "text"]);
    expect(stopped.live).toEqual({ reasoning: "", text: "" });
  });
});
