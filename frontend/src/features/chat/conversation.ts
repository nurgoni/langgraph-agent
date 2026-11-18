/**
 * State percakapan dan konversinya ke message assistant-ui (FR-43).
 *
 * Spesifikasi acuan adalah `MessageRenderer` Streamlit: reasoning → token → message utuh, hasil
 * tool dipasangkan ke tool call lewat `tool_call_id`, dan message sub-agent (`agent`) dikelompokkan
 * per expert (FR-23). Semua message setelah satu pesan user digabung menjadi satu message asisten,
 * seperti blok chat Streamlit.
 */
import type { ThreadMessageLike } from "@assistant-ui/react";

import type { ChatMessage, StreamEvent } from "@/api/stream-event";
import type { ArtifactRef } from "@/features/artifacts/artifacts-service";

/** Satu baris riwayat: message dari service, error run, atau run yang dihentikan user. */
export type ChatEntry =
  | { kind: "message"; message: ChatMessage }
  | { kind: "error"; text: string }
  | { kind: "cancelled" };

/** Teks yang sedang di-stream untuk jawaban AI berikutnya (frame `reasoning` dan `token`). */
export interface LiveReply {
  reasoning: string;
  text: string;
}

export interface ConversationState {
  entries: readonly ChatEntry[];
  live: LiveReply;
}

type MessagePart = Exclude<ThreadMessageLike["content"], string>[number];
type MessageStatus = NonNullable<ThreadMessageLike["status"]>;
// Argumen tool di kontrak bertipe `{[key: string]: unknown}`, assistant-ui meminta JSON readonly.
type ToolArgs = NonNullable<Extract<MessagePart, { type: "tool-call" }>["args"]>;

export const CUSTOM_DATA_PART_NAME = "custom";
/**
 * Artifact di jawaban asisten (part `data`) dan di pesan user (`metadata.custom`), memakai nama
 * yang sama. Keduanya dirender sebagai kartu yang membuka panel preview (F38).
 */
export const ARTIFACTS_DATA_PART_NAME = "artifacts";
export const EMPTY_LIVE: LiveReply = { reasoning: "", text: "" };
export const EMPTY_CONVERSATION: ConversationState = { entries: [], live: EMPTY_LIVE };

const RUNNING: MessageStatus = { type: "running" };
const COMPLETE: MessageStatus = { type: "complete", reason: "stop" };
const TRUNCATED: MessageStatus = { type: "incomplete", reason: "length" };
const CANCELLED: MessageStatus = { type: "incomplete", reason: "cancelled" };

/** Percakapan dari riwayat thread (`POST /history`). */
export function conversationFromHistory(messages: readonly ChatMessage[]): ConversationState {
  return {
    entries: messages.map((message) => ({ kind: "message", message })),
    live: EMPTY_LIVE,
  };
}

/** Tambahkan pesan user yang baru dikirim, beserta lampirannya. */
export function appendHuman(
  state: ConversationState,
  text: string,
  artifacts: readonly ArtifactRef[] = [],
): ConversationState {
  const message: ChatMessage = { type: "human", content: text, artifacts: [...artifacts] };
  return { entries: [...state.entries, { kind: "message", message }], live: EMPTY_LIVE };
}

/** Tambahkan error atau penghentian run. Teks yang sudah di-stream disimpan sebagai jawaban. */
export function appendRunEnd(
  state: ConversationState,
  entry: Exclude<ChatEntry, { kind: "message" }>,
): ConversationState {
  const entries = [...state.entries];
  if (state.live.text !== "" || state.live.reasoning !== "") {
    const partial: ChatMessage = {
      type: "ai",
      content: state.live.text,
      reasoning: state.live.reasoning || null,
    };
    entries.push({ kind: "message", message: partial });
  }
  entries.push(entry);
  return { entries, live: EMPTY_LIVE };
}

/**
 * Terapkan satu event SSE.
 *
 * Message AI menggantikan teks yang di-stream. Reasoning yang di-stream dipakai jika message tidak
 * membawanya sendiri.
 */
export function applyStreamEvent(state: ConversationState, event: StreamEvent): ConversationState {
  switch (event.type) {
    case "reasoning":
      return { ...state, live: { ...state.live, reasoning: state.live.reasoning + event.content } };
    case "token":
      return { ...state, live: { ...state.live, text: state.live.text + event.content } };
    case "error":
      return appendRunEnd(state, { kind: "error", text: event.content });
    case "message":
      return appendServiceMessage(state, event.content);
    default:
      return state;
  }
}

function appendServiceMessage(state: ConversationState, message: ChatMessage): ConversationState {
  if (message.type !== "ai") {
    return { ...state, entries: [...state.entries, { kind: "message", message }] };
  }
  const reasoning = message.reasoning || state.live.reasoning || null;
  const entry: ChatEntry = { kind: "message", message: { ...message, reasoning } };
  return { entries: [...state.entries, entry], live: EMPTY_LIVE };
}

/**
 * Message untuk assistant-ui: satu message user per pesan human, dan satu message asisten berisi
 * semua part sampai pesan human berikutnya.
 *
 * @param state Percakapan.
 * @param isRunning `true` selama run berjalan: teks live ditambahkan dan message terakhir berstatus
 *   `running`.
 */
export function toThreadMessages(
  state: ConversationState,
  isRunning: boolean,
): ThreadMessageLike[] {
  const builder = new ThreadMessageBuilder();
  state.entries.forEach((entry, index) => builder.add(entry, index));
  if (isRunning) {
    builder.addLive(state.live, state.entries.length);
  }
  return builder.build();
}

/** Status message asisten yang sedang disusun. */
interface AssistantDraft {
  id: string;
  parts: MessagePart[];
  toolCallIndex: Map<string, number>;
  status: MessageStatus;
  running: boolean;
}

/**
 * Menyusun message assistant-ui dari entri berurutan.
 *
 * Class karena menyimpan state selama satu pass: message asisten aktif dan indeks tool call yang
 * menunggu hasilnya.
 */
class ThreadMessageBuilder {
  private readonly messages: ThreadMessageLike[] = [];
  private draft: AssistantDraft | null = null;

  add(entry: ChatEntry, index: number): void {
    if (entry.kind === "error") {
      this.assistant(index).status = { type: "incomplete", reason: "error", error: entry.text };
      return;
    }
    if (entry.kind === "cancelled") {
      this.assistant(index).status = CANCELLED;
      return;
    }
    this.addMessage(entry.message, index);
  }

  addLive(live: LiveReply, index: number): void {
    const draft = this.assistant(index);
    draft.running = true;
    if (live.reasoning !== "") {
      draft.parts.push({ type: "reasoning", text: live.reasoning });
    }
    if (live.text !== "") {
      draft.parts.push({ type: "text", text: live.text });
    }
  }

  build(): ThreadMessageLike[] {
    this.closeAssistant();
    return this.messages;
  }

  private addMessage(message: ChatMessage, index: number): void {
    switch (message.type) {
      case "human":
        this.closeAssistant();
        this.messages.push({
          id: `user-${index}`,
          role: "user",
          content: message.content,
          metadata: { custom: { [ARTIFACTS_DATA_PART_NAME]: message.artifacts ?? [] } },
        });
        return;
      case "ai":
        this.addAiMessage(message, index);
        return;
      case "tool":
        this.addToolResult(message, index);
        return;
      case "custom":
        this.assistant(index).parts.push({
          type: "data",
          name: CUSTOM_DATA_PART_NAME,
          data: message.custom_data ?? {},
        });
        return;
    }
  }

  private addAiMessage(message: ChatMessage, index: number): void {
    const draft = this.assistant(index);
    const parentId = message.agent ?? undefined;
    if (message.reasoning) {
      draft.parts.push({ type: "reasoning", text: message.reasoning, parentId });
    }
    if (message.content !== "") {
      draft.parts.push({ type: "text", text: message.content, parentId });
    }
    for (const call of message.tool_calls ?? []) {
      const toolCallId = call.id ?? `${draft.id}-tool-${draft.parts.length}`;
      draft.toolCallIndex.set(toolCallId, draft.parts.length);
      draft.parts.push({
        type: "tool-call",
        toolCallId,
        toolName: call.name,
        args: (call.args ?? {}) as ToolArgs,
        argsText: JSON.stringify(call.args ?? {}, null, 2),
        parentId,
      });
    }
    if (message.truncated) {
      draft.status = TRUNCATED;
    }
    this.addArtifacts(draft, message);
  }

  /** Kartu artifact yang dibagikan message ini (misalnya hasil `share_file`). */
  private addArtifacts(draft: AssistantDraft, message: ChatMessage): void {
    const artifacts = message.artifacts ?? [];
    if (artifacts.length === 0) {
      return;
    }
    draft.parts.push({ type: "data", name: ARTIFACTS_DATA_PART_NAME, data: artifacts });
  }

  /** Isi hasil tool call yang cocok dengan `tool_call_id`, atau tambahkan part tool baru. */
  private addToolResult(message: ChatMessage, index: number): void {
    const draft = this.assistant(index);
    const callIndex = draft.toolCallIndex.get(message.tool_call_id ?? "");
    const call = callIndex === undefined ? undefined : draft.parts[callIndex];
    if (call?.type === "tool-call" && callIndex !== undefined) {
      draft.parts[callIndex] = { ...call, result: message.content };
      this.addArtifacts(draft, message);
      return;
    }
    draft.parts.push({
      type: "tool-call",
      toolCallId: message.tool_call_id ?? `${draft.id}-result-${draft.parts.length}`,
      toolName: "result",
      args: {},
      result: message.content,
      parentId: message.agent ?? undefined,
    });
    this.addArtifacts(draft, message);
  }

  private assistant(index: number): AssistantDraft {
    if (this.draft === null) {
      this.draft = {
        id: `assistant-${index}`,
        parts: [],
        toolCallIndex: new Map(),
        status: COMPLETE,
        running: false,
      };
    }
    return this.draft;
  }

  private closeAssistant(): void {
    if (this.draft === null) {
      return;
    }
    const { id, parts, status, running } = this.draft;
    this.messages.push({ id, role: "assistant", content: parts, status: running ? RUNNING : status });
    this.draft = null;
  }
}
