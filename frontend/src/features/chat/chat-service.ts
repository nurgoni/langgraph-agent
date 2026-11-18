/**
 * Request chat lewat client bertipe: run streaming dan riwayat thread, untuk chat umum (agent
 * default) atau chat di dalam project (`/projects/{project_id}/...`, F34).
 */
import { type ApiClient, errorDetail } from "@/api/client";
import { UNREACHABLE_MESSAGE } from "@/api/service-error";
import type { ChatMessage, StreamEvent } from "@/api/stream-event";
import { readStreamEvents } from "@/features/chat/sse";

export { UNREACHABLE_MESSAGE };
export const THREAD_ID_HEADER = "X-Thread-Id";
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
  private readonly projectId: string | null;

  /**
   * @param api Client bertipe ke agent service.
   * @param projectId Project tempat chat berjalan, atau `null` untuk chat umum.
   */
  constructor(api: ApiClient, projectId: string | null = null) {
    this.api = api;
    this.projectId = projectId;
  }

  /**
   * Mulai run dengan token streaming (`POST /stream` atau `POST /projects/{id}/stream`).
   *
   * @throws ChatServiceError Jika service menolak request atau tidak terjangkau.
   * @throws DOMException `AbortError` jika `signal` dibatalkan.
   */
  async startRun(request: ChatRequest, signal: AbortSignal): Promise<ChatRun> {
    const body = {
      message: request.message,
      thread_id: request.threadId,
      model: request.model,
      stream_tokens: true,
    };
    const projectId = this.projectId;
    const { data, error, response } = await this.send(() =>
      projectId === null
        ? this.api.POST("/stream", { body, parseAs: "stream", signal })
        : this.api.POST("/projects/{project_id}/stream", {
            params: { path: { project_id: projectId } },
            body,
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
   * Riwayat thread milik user (`POST /history` atau `POST /projects/{id}/history`).
   *
   * @throws ChatServiceError Jika thread tidak ditemukan (404) atau service tidak terjangkau.
   */
  async loadHistory(threadId: string): Promise<ChatMessage[]> {
    const body = { thread_id: threadId };
    const projectId = this.projectId;
    const { data, error, response } = await this.send(() =>
      projectId === null
        ? this.api.POST("/history", { body })
        : this.api.POST("/projects/{project_id}/history", {
            params: { path: { project_id: projectId } },
            body,
          }),
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
