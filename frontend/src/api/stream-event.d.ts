/**
 * File ini digenerate dari contracts/stream-event.schema.json. Jangan diedit manual.
 * Generate ulang: corepack pnpm generate:api
 */

/**
 * One Server-Sent Event frame from POST /{agent_id}/stream. Each frame is sent as `data: <json>`, and the stream always ends with the literal `data: [DONE]`, which is not JSON.
 */
export type StreamEvent = ReasoningEvent | TokenEvent | MessageEvent | ErrorEvent;
export type Content = string;
export type Type = "reasoning";
export type Content1 = string;
export type Type1 = "token";
/**
 * Sub-agent (expert) yang membuat message ini, atau kosong untuk agent utama.
 */
export type Agent = string | null;
export type Content2 = string;
export type JsonValue = unknown;
/**
 * Untuk message `ai`: pemikiran model sebelum menjawab, jika model mengirimnya.
 */
export type Reasoning = string | null;
/**
 * ID run agent yang menghasilkan message.
 */
export type RunId = string | null;
/**
 * Untuk message `tool`: ID tool call yang dijawab.
 */
export type ToolCallId = string | null;
/**
 * ID dari provider, dipakai oleh ToolMessage.
 */
export type Id = string | null;
export type Name = string;
export type ToolCalls = ToolCall[];
/**
 * Untuk message `ai`: jawaban berhenti karena batas token (`LLM_MAX_TOKENS`).
 */
export type Truncated = boolean;
/**
 * Peran message.
 */
export type Type2 = "human" | "ai" | "tool" | "custom";
export type Type3 = "message";
export type Content3 = string;
export type Type4 = "error";

/**
 * Potongan pemikiran model sebelum jawaban (FR-29), dikirim saat `stream_tokens=True`.
 */
export interface ReasoningEvent {
  content: Content;
  type?: Type;
}
/**
 * Potongan teks dari LLM, dikirim saat `stream_tokens=True`.
 */
export interface TokenEvent {
  content: Content1;
  type?: Type1;
}
/**
 * Message utuh: jawaban AI, tool call, hasil tool, atau event custom.
 */
export interface MessageEvent {
  content: ChatMessage;
  type?: Type3;
}
/**
 * Satu message dalam percakapan, dalam bentuk netral (bukan objek LangChain).
 */
export interface ChatMessage {
  agent?: Agent;
  content: Content2;
  custom_data?: CustomData;
  reasoning?: Reasoning;
  response_metadata?: ResponseMetadata;
  run_id?: RunId;
  tool_call_id?: ToolCallId;
  tool_calls?: ToolCalls;
  truncated?: Truncated;
  type: Type2;
}
/**
 * Payload untuk message `custom` (event khusus agent).
 */
export interface CustomData {
  [k: string]: JsonValue;
}
/**
 * Metadata dari provider, misalnya jumlah token.
 */
export interface ResponseMetadata {
  [k: string]: JsonValue;
}
/**
 * Permintaan model untuk memanggil satu tool.
 */
export interface ToolCall {
  args?: Args;
  id?: Id;
  name: Name;
}
export interface Args {
  [k: string]: JsonValue;
}
/**
 * Error saat agent berjalan. Stream tetap diakhiri `[DONE]` setelah event ini.
 */
export interface ErrorEvent {
  content: Content3;
  type?: Type4;
}
