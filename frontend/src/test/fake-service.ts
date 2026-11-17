/**
 * `fetch` palsu yang meniru agent service di balik proxy `/api`, untuk test tanpa network.
 */
import type { TokenResponse } from "@/auth/session";

export const VALID_PASSWORD = "correct-horse";
export const TOKEN_TTL_SECONDS = 3600;

export interface FakeServiceOptions {
  /** Jawaban `/info` 401, seperti token yang dicabut atau kedaluwarsa di service. */
  rejectToken?: boolean;
}

export interface RecordedRequest {
  method: string;
  path: string;
  authorization: string | null;
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
    this.requests.push({
      method: request.method,
      path,
      authorization: request.headers.get("Authorization"),
    });
    if (path === "/api/auth/login") {
      return this.login(request);
    }
    if (path === "/api/info") {
      return this.info(request);
    }
    return json({ detail: "Not Found" }, 404);
  };

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
        models: ["fake"],
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
