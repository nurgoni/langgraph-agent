/**
 * `fetch` palsu yang meniru agent service di balik proxy `/api`, untuk test tanpa network.
 */
import type { TokenResponse } from "@/auth/session";

export const VALID_PASSWORD = "correct-horse";
export const TOKEN_TTL_SECONDS = 3600;

export const NEW_THREAD_ID = "thread-new";
const DONE_FRAME = "data: [DONE]\n\n";

export interface FakeServiceOptions {
  /** Jawaban `/info` 401, seperti token yang dicabut atau kedaluwarsa di service. */
  rejectToken?: boolean;
  /** Body SSE untuk setiap `POST /stream`, berurutan. Yang terakhir dipakai ulang. */
  streams?: string[];
  /** Riwayat per thread untuk `POST /history`. Thread lain dijawab 404. */
  histories?: Record<string, unknown>;
}

export interface RecordedRequest {
  method: string;
  path: string;
  authorization: string | null;
  body: unknown;
}

export class FakeService {
  readonly requests: RecordedRequest[] = [];
  private readonly options: FakeServiceOptions;

  constructor(options: FakeServiceOptions = {}) {
    this.options = options;
  }

  readonly fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = new Request(input, init);
    const path = new URL(request.url).pathname;
    const body: unknown = request.method === "POST" ? await request.clone().json() : null;
    this.requests.push({
      method: request.method,
      path,
      authorization: request.headers.get("Authorization"),
      body,
    });
    if (path === "/api/auth/login") {
      return this.login(request);
    }
    if (path === "/api/info") {
      return this.info(request);
    }
    if (path === "/api/stream") {
      return this.stream(body as { thread_id?: string | null });
    }
    if (path === "/api/history") {
      return this.history(body as { thread_id: string });
    }
    return json({ detail: "Not Found" }, 404);
  };

  /** Request yang dikirim ke `path`, urut waktu. */
  requestsTo(path: string): RecordedRequest[] {
    return this.requests.filter((request) => request.path === path);
  }

  private stream(body: { thread_id?: string | null }): Response {
    const streams = this.options.streams ?? [DONE_FRAME];
    const index = Math.min(this.requestsTo("/api/stream").length - 1, streams.length - 1);
    return new Response(streams[index], {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "X-Thread-Id": body.thread_id ?? NEW_THREAD_ID,
      },
    });
  }

  private history(body: { thread_id: string }): Response {
    const history = this.options.histories?.[body.thread_id];
    if (history === undefined) {
      return json({ detail: "Thread not found" }, 404);
    }
    return json(history, 200);
  }

  private async login(request: Request): Promise<Response> {
    const body = (await request.json()) as { username: string; password: string };
    if (body.password !== VALID_PASSWORD) {
      return json({ detail: "Invalid username or password" }, 401);
    }
    const token: TokenResponse = {
      access_token: `token-for-${body.username}`,
      token_type: "bearer",
      expires_in: TOKEN_TTL_SECONDS,
      user_id: "u1",
      username: body.username,
      role: "user",
    };
    return json(token, 200);
  }

  private info(request: Request): Response {
    if (this.options.rejectToken || request.headers.get("Authorization") === null) {
      return json({ detail: "Invalid or expired token" }, 401);
    }
    return json(
      {
        agents: [
          { key: "chatbot", description: "Chat", config_schema: {} },
          { key: "research-assistant", description: "Research", config_schema: {} },
        ],
        models: ["fake", "qwen3.5:9b"],
        default_agent: "chatbot",
        default_model: "fake",
      },
      200,
    );
  }
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
