/**
 * `fetch` palsu yang meniru agent service di balik proxy `/api`, untuk test tanpa network.
 *
 * Menyimpan state di memori: thread per scope (chat umum atau project), project, dan skill,
 * sehingga alur buat → chat → rename → hapus bisa dites lewat UI.
 */
import type { components } from "@/api/schema";
import type { TokenResponse } from "@/auth/session";

type Project = components["schemas"]["Project"];
type ProjectCreate = components["schemas"]["ProjectCreate"];
type ProjectUpdate = components["schemas"]["ProjectUpdate"];
type SkillSummary = components["schemas"]["SkillSummary"];
type ThreadSummary = components["schemas"]["ThreadSummary"];

export const VALID_PASSWORD = "correct-horse";
export const TOKEN_TTL_SECONDS = 3600;

export const NEW_THREAD_ID = "thread-new";
export const DEFAULT_AGENT = "chatbot";
const DONE_FRAME = "data: [DONE]\n\n";
const GENERAL_SCOPE = "general";
const TITLE_MAX_LENGTH = 60;
const FIXED_TIME = "2026-11-18T08:00:00Z";

export const SKILLS: SkillSummary[] = [
  {
    id: "builtin/research-report",
    name: "research-report",
    description: "Write a sourced research report.",
    scope: "builtin",
    version: "1",
    read_only: true,
    resources: [],
  },
  {
    id: "builtin/meeting-notes",
    name: "meeting-notes",
    description: "Turn a transcript into meeting notes.",
    scope: "builtin",
    version: "1",
    read_only: true,
    resources: [],
  },
];

export const BUILTIN_PROJECT: Project = {
  id: "builtin-research",
  name: "Research",
  description: "Sourced research reports.",
  scope: "builtin",
  read_only: true,
  base_agent_id: "research-assistant",
  model: null,
  instructions: "Cite every source.",
  skill_ids: ["builtin/research-report"],
  settings: { max_tokens: null, tool_approval: "never" },
  created_at: FIXED_TIME,
  updated_at: FIXED_TIME,
};

export interface FakeServiceOptions {
  /** Jawaban `/info` 401, seperti token yang dicabut atau kedaluwarsa di service. */
  rejectToken?: boolean;
  /** Body SSE untuk setiap request stream, berurutan. Yang terakhir dipakai ulang. */
  streams?: string[];
  /** Riwayat per thread untuk request history. Thread lain dijawab 404. */
  histories?: Record<string, unknown>;
  /** Thread awal per scope: `general` untuk chat umum, atau id project. */
  threads?: Record<string, ThreadSummary[]>;
  /** Project awal. Default: satu project built-in. */
  projects?: Project[];
}

export interface RecordedRequest {
  method: string;
  path: string;
  authorization: string | null;
  body: unknown;
}

const PROJECT_PATH = /^\/api\/projects\/([^/]+)$/;
const PROJECT_ROUTE = /^\/api\/projects\/([^/]+)\/(stream|history|threads)$/;
const PROJECT_THREAD_PATH = /^\/api\/projects\/([^/]+)\/threads\/([^/]+)$/;
const THREAD_PATH = /^\/api\/threads\/([^/]+)$/;

export class FakeService {
  readonly requests: RecordedRequest[] = [];
  private readonly options: FakeServiceOptions;
  private readonly threads = new Map<string, ThreadSummary[]>();
  private readonly projects: Project[];
  private createdProjects = 0;

  constructor(options: FakeServiceOptions = {}) {
    this.options = options;
    this.projects = [...(options.projects ?? [BUILTIN_PROJECT])];
    for (const [scope, threads] of Object.entries(options.threads ?? {})) {
      this.threads.set(scope, [...threads]);
    }
  }

  readonly fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = new Request(input, init);
    const path = decodeURIComponent(new URL(request.url).pathname);
    const body: unknown = hasJsonBody(request) ? await request.clone().json() : null;
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
    return this.route(request.method, path, body);
  };

  /** Request yang dikirim ke `path`, urut waktu. */
  requestsTo(path: string, method?: string): RecordedRequest[] {
    return this.requests.filter(
      (request) => request.path === path && (method === undefined || request.method === method),
    );
  }

  /** Thread yang tersimpan di scope (`general` atau id project). */
  threadsIn(scope: string): ThreadSummary[] {
    return this.threads.get(scope) ?? [];
  }

  private route(method: string, path: string, body: unknown): Response {
    if (path === "/api/stream") {
      return this.stream(GENERAL_SCOPE, body);
    }
    if (path === "/api/history") {
      return this.history(body);
    }
    if (path === "/api/threads") {
      return json({ threads: this.threadsIn(GENERAL_SCOPE) }, 200);
    }
    if (path === "/api/skills") {
      return json({ skills: SKILLS }, 200);
    }
    if (path === "/api/projects") {
      return method === "POST" ? this.createProject(body) : json({ projects: this.projects }, 200);
    }
    return this.routeByPattern(method, path, body);
  }

  private routeByPattern(method: string, path: string, body: unknown): Response {
    const thread = THREAD_PATH.exec(path);
    if (thread !== null) {
      return this.changeThread(method, GENERAL_SCOPE, thread[1] ?? "", body);
    }
    const projectThread = PROJECT_THREAD_PATH.exec(path);
    if (projectThread !== null) {
      return this.changeThread(method, projectThread[1] ?? "", projectThread[2] ?? "", body);
    }
    const projectRoute = PROJECT_ROUTE.exec(path);
    if (projectRoute !== null) {
      return this.projectRoute(projectRoute[1] ?? "", projectRoute[2] ?? "", body);
    }
    const project = PROJECT_PATH.exec(path);
    if (project !== null) {
      return this.changeProject(method, project[1] ?? "", body);
    }
    return json({ detail: "Not Found" }, 404);
  }

  private projectRoute(projectId: string, action: string, body: unknown): Response {
    if (this.findProject(projectId) === undefined) {
      return json({ detail: "Project not found" }, 404);
    }
    if (action === "stream") {
      return this.stream(projectId, body);
    }
    if (action === "history") {
      return this.history(body);
    }
    return json({ threads: this.threadsIn(projectId) }, 200);
  }

  private stream(scope: string, body: unknown): Response {
    const { message, thread_id: threadId } = body as { message: string; thread_id?: string | null };
    const streams = this.options.streams ?? [DONE_FRAME];
    const index = Math.min(this.requests.filter(isStream).length - 1, streams.length - 1);
    const usedThreadId = threadId ?? NEW_THREAD_ID;
    if (threadId === null || threadId === undefined) {
      this.addThread(scope, usedThreadId, message);
    }
    return new Response(streams[index], {
      status: 200,
      headers: { "Content-Type": "text/event-stream", "X-Thread-Id": usedThreadId },
    });
  }

  private addThread(scope: string, threadId: string, message: string): void {
    const threads = this.threadsIn(scope).filter((thread) => thread.thread_id !== threadId);
    const summary: ThreadSummary = {
      thread_id: threadId,
      agent_id: DEFAULT_AGENT,
      project_id: scope === GENERAL_SCOPE ? null : scope,
      title: message.slice(0, TITLE_MAX_LENGTH),
      updated_at: FIXED_TIME,
    };
    this.threads.set(scope, [summary, ...threads]);
  }

  private history(body: unknown): Response {
    const { thread_id: threadId } = body as { thread_id: string };
    const history = this.options.histories?.[threadId];
    if (history === undefined) {
      return json({ detail: "Thread not found" }, 404);
    }
    return json(history, 200);
  }

  private changeThread(method: string, scope: string, threadId: string, body: unknown): Response {
    const threads = this.threadsIn(scope);
    const existing = threads.find((thread) => thread.thread_id === threadId);
    if (existing === undefined) {
      return json({ detail: "Thread not found" }, 404);
    }
    if (method === "DELETE") {
      this.threads.set(
        scope,
        threads.filter((thread) => thread !== existing),
      );
      return new Response(null, { status: 204 });
    }
    const title = (body as { title: string }).title.trim();
    const renamed = { ...existing, title };
    this.threads.set(
      scope,
      threads.map((thread) => (thread === existing ? renamed : thread)),
    );
    return json(renamed, 200);
  }

  private createProject(body: unknown): Response {
    const input = body as ProjectCreate;
    if (input.base_agent_id !== DEFAULT_AGENT && input.base_agent_id !== "research-assistant") {
      return json({ detail: `Unknown agent: ${input.base_agent_id}` }, 422);
    }
    this.createdProjects += 1;
    const project: Project = {
      id: `project-${this.createdProjects}`,
      name: input.name.trim(),
      description: input.description ?? "",
      scope: "user",
      read_only: false,
      base_agent_id: input.base_agent_id,
      model: input.model ?? null,
      instructions: input.instructions ?? "",
      skill_ids: input.skill_ids ?? [],
      settings: {
        max_tokens: input.settings?.max_tokens ?? null,
        tool_approval: input.settings?.tool_approval ?? "never",
      },
      created_at: FIXED_TIME,
      updated_at: FIXED_TIME,
    };
    this.projects.push(project);
    return json(project, 201);
  }

  private changeProject(method: string, projectId: string, body: unknown): Response {
    const project = this.findProject(projectId);
    if (project === undefined) {
      return json({ detail: "Project not found" }, 404);
    }
    if (method === "GET") {
      return json(project, 200);
    }
    if (project.read_only) {
      return json({ detail: "Built-in projects are read-only" }, 403);
    }
    const index = this.projects.indexOf(project);
    if (method === "DELETE") {
      this.projects.splice(index, 1);
      this.threads.delete(projectId);
      return new Response(null, { status: 204 });
    }
    const updated = withUpdate(project, body as ProjectUpdate);
    this.projects[index] = updated;
    return json(updated, 200);
  }

  private findProject(projectId: string): Project | undefined {
    return this.projects.find((project) => project.id === projectId);
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
          { key: DEFAULT_AGENT, description: "Chat", config_schema: {} },
          { key: "research-assistant", description: "Research", config_schema: {} },
        ],
        models: ["fake", "qwen3.5:9b"],
        default_agent: DEFAULT_AGENT,
        default_model: "fake",
      },
      200,
    );
  }
}

function isStream(request: RecordedRequest): boolean {
  return request.path.endsWith("/stream");
}

function hasJsonBody(request: Request): boolean {
  return request.method === "POST" || request.method === "PATCH";
}

function withUpdate(project: Project, changes: ProjectUpdate): Project {
  return {
    ...project,
    name: changes.name ?? project.name,
    description: changes.description ?? project.description,
    model: changes.model === undefined ? project.model : changes.model,
    instructions: changes.instructions ?? project.instructions,
    skill_ids: changes.skill_ids ?? project.skill_ids,
    settings: changes.settings ?? project.settings,
  };
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
