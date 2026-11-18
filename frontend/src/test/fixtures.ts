/**
 * Rekaman SSE dan riwayat asli dari agent service (Ollama `qwen3.5:9b`, F33), dipakai sebagai
 * fixture test. Direkam dengan skrip smoke di database sementara; lihat `__fixtures__/README.md`.
 */
import interruptSse from "@/features/chat/__fixtures__/interrupt.sse?raw";
import reasoningSse from "@/features/chat/__fixtures__/reasoning.sse?raw";
import subAgentsHistory from "@/features/chat/__fixtures__/sub-agents.history.json";
import subAgentsSse from "@/features/chat/__fixtures__/sub-agents.sse?raw";
import toolCallsHistory from "@/features/chat/__fixtures__/tool-calls.history.json";
import toolCallsSse from "@/features/chat/__fixtures__/tool-calls.sse?raw";
import truncatedHistory from "@/features/chat/__fixtures__/truncated.history.json";
import truncatedSse from "@/features/chat/__fixtures__/truncated.sse?raw";

export const SSE_FIXTURES = {
  reasoning: reasoningSse,
  toolCalls: toolCallsSse,
  subAgents: subAgentsSse,
  truncated: truncatedSse,
  interrupt: interruptSse,
};

export const HISTORY_FIXTURES = {
  toolCalls: toolCallsHistory,
  subAgents: subAgentsHistory,
  truncated: truncatedHistory,
};

/** Body SSE berisi satu frame error, seperti saat agent gagal di tengah run. */
export const ERROR_SSE = 'data: {"type":"error","content":"Model provider is unavailable"}\n\ndata: [DONE]\n\n';
