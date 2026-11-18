/**
 * Request chat ke agent default lewat client bertipe: run streaming dan riwayat thread.
 */
import { type ApiClient, errorDetail } from "@/api/client";
import type { ChatMessage, StreamEvent } from "@/api/stream-event";
import { readStreamEvents } from "@/features/chat/sse";

export const THREAD_ID_HEADER = "X-Thread-Id";
export const UNREACHABLE_MESSAGE = "Cannot reach the agent service. Try again later.";
const RUN_FAILED_MESSAGE = "The agent service could not start the run.";
const HISTORY_FAILED_MESSAGE = "Cannot load this conversation.";

/** Request gagal. `status` berisi kode HTTP, atau `null` jika service tidak terjangkau. */
export class ChatServiceError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.name = "ChatServiceError";
    this.status = status;
  }
}

export interface ChatRequest {
  message: string;
  /** Thread yang dilanjutkan, atau `null` untuk thread baru. */
  threadId: string | null;
  /** Model pilihan user, atau `null` untuk model default service. */
  model: string | null;
}

export interface ChatRun {
  /** Thread yang dipakai run, dari header `X-Thread-Id`. */
  threadId: string;
  events: AsyncGenerator<StreamEvent>;
}

export class ChatService {
  private readonly api: ApiClient;

  constructor(api: ApiClient) {
    this.api = api;
  }

  /**
   * Mulai run dengan token streaming (`POST /stream`).
   *
   * @throws ChatServiceError Jika service menolak request atau tidak terjangkau.
   * @throws DOMException `AbortError` jika `signal` dibatalkan.
   */
  async startRun(request: ChatRequest, signal: AbortSignal): Promise<ChatRun> {
    const { data, error, response } = await this.send(() =>
      this.api.POST("/stream", {
        body: {
          message: request.message,
          thread_id: request.threadId,
          model: request.model,
          stream_tokens: true,
        },
        parseAs: "stream",
        signal,
      }),
    );
    const threadId = response.headers.get(THREAD_ID_HEADER);
    if (data === null || data === undefined || threadId === null) {
      throw new ChatServiceError(errorDetail(error, RUN_FAILED_MESSAGE), response.status);
    }
    return { threadId, events: readStreamEvents(data) };
  }

  /**
   * Riwayat thread milik user (`POST /history`).
   *
   * @throws ChatServiceError Jika thread tidak ditemukan (404) atau service tidak terjangkau.
   */
  async loadHistory(threadId: string): Promise<ChatMessage[]> {
    const { data, error, response } = await this.send(() =>
      this.api.POST("/history", { body: { thread_id: threadId } }),
    );
    if (data === undefined) {
      throw new ChatServiceError(errorDetail(error, HISTORY_FAILED_MESSAGE), response.status);
    }
    return data.messages;
  }

  /** Jalankan request, dan ubah kegagalan jaringan menjadi `ChatServiceError`. */
  private async send<T>(request: () => Promise<T>): Promise<T> {
    try {
      return await request();
    } catch (caught) {
      if (caught instanceof TypeError) {
        throw new ChatServiceError(UNREACHABLE_MESSAGE, null);
      }
      throw caught;
    }
  }
}
