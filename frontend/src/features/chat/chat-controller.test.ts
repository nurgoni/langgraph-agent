import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/api/client";
import {
  ChatController,
  THREAD_NOT_FOUND_MESSAGE,
} from "@/features/chat/chat-controller";
import { ChatService, UNREACHABLE_MESSAGE } from "@/features/chat/chat-service";
import { toThreadMessages } from "@/features/chat/conversation";
import { FakeService, NEW_THREAD_ID } from "@/test/fake-service";
import { HISTORY_FIXTURES, SSE_FIXTURES } from "@/test/fixtures";

const BASE_URL = "http://web.test/api";

function controllerFor(fetch: typeof globalThis.fetch) {
  const api = createApiClient({
    getAccessToken: () => "jwt",
    onUnauthorized: vi.fn(),
    fetch,
    baseUrl: BASE_URL,
  });
  const controller = new ChatController(new ChatService(api));
  const created = vi.fn();
  const finished = vi.fn();
  controller.setRunListeners({ onThreadCreated: created, onRunFinished: finished });
  return { controller, created, finished };
}

/** `fetch` yang menjawab `/stream` dengan body yang tidak pernah selesai sampai dibatalkan. */
function hangingStreamFetch(): typeof globalThis.fetch {
  return (input, init) => {
    const signal = new Request(input, init).signal;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"type":"token","content":"Partial"}\n\n'));
        signal.addEventListener("abort", () => controller.error(signal.reason));
      },
    });
    return Promise.resolve(
      new Response(body, { headers: { "X-Thread-Id": "thread-hanging" } }),
    );
  };
}

/** URL request tanpa membaca body-nya (membuat `Request` baru akan memakai body). */
function urlOf(input: RequestInfo | URL): string {
  if (input instanceof Request) {
    return input.url;
  }
  return input instanceof URL ? input.href : input;
}

describe("ChatController", () => {
  it("sends the chosen model with token streaming and announces the new thread", async () => {
    const service = new FakeService({ streams: [SSE_FIXTURES.interrupt] });
    const { controller, created } = controllerFor(service.fetch);

    await controller.send("Hi", "qwen3.5:9b");

    expect(service.requestsTo("/api/stream")[0]?.body).toEqual({
      message: "Hi",
      thread_id: null,
      model: "qwen3.5:9b",
      stream_tokens: true,
      artifact_ids: [],
    });
    expect(created).toHaveBeenCalledWith(NEW_THREAD_ID);
    expect(controller.getSnapshot()).toMatchObject({ threadId: NEW_THREAD_ID, isRunning: false });
  });

  it("continues the same thread on the next message", async () => {
    const service = new FakeService({ streams: [SSE_FIXTURES.interrupt] });
    const { controller, created, finished } = controllerFor(service.fetch);

    await controller.send("Hi", null);
    await controller.send("My name is Rani", null);

    const bodies = service.requestsTo("/api/stream").map((request) => request.body);
    expect(bodies[1]).toMatchObject({ thread_id: NEW_THREAD_ID, model: null });
    expect(created).toHaveBeenCalledOnce();
    expect(finished).toHaveBeenCalledTimes(2);
    expect(toThreadMessages(controller.getSnapshot().conversation, false)).toHaveLength(4);
  });

  it("runs in a project through the project routes (F34)", async () => {
    const service = new FakeService({ streams: [SSE_FIXTURES.interrupt] });
    const api = createApiClient({
      getAccessToken: () => "jwt",
      onUnauthorized: vi.fn(),
      fetch: service.fetch,
      baseUrl: BASE_URL,
    });
    const controller = new ChatController(new ChatService(api, "project-1"));

    await controller.send("Hi", null);
    controller.openThread("thread-other");

    expect(service.requestsTo("/api/projects/project-1/stream")[0]?.body).toMatchObject({
      message: "Hi",
    });
    await vi.waitFor(() =>
      expect(service.requestsTo("/api/projects/project-1/history")[0]?.body).toEqual({
        thread_id: "thread-other",
      }),
    );
    expect(service.requestsTo("/api/stream")).toEqual([]);
  });

  it("stops a run on cancel and keeps the streamed text", async () => {
    const { controller, finished } = controllerFor(hangingStreamFetch());

    const sending = controller.send("Write an essay", null);
    await vi.waitFor(() => expect(controller.getSnapshot().conversation.live.text).toBe("Partial"));
    controller.cancel();
    await sending;

    const snapshot = controller.getSnapshot();
    const reply = toThreadMessages(snapshot.conversation, snapshot.isRunning)[1];
    expect(snapshot.isRunning).toBe(false);
    expect(reply?.status).toEqual({ type: "incomplete", reason: "cancelled" });
    expect(reply?.content).toEqual([{ type: "text", text: "Partial" }]);
    expect(finished).toHaveBeenCalledOnce();
  });

  it("drops a running reply when the user opens another thread", async () => {
    const history = new FakeService({ histories: { t1: HISTORY_FIXTURES.toolCalls } });
    const hanging = hangingStreamFetch();
    const { controller } = controllerFor((input, init) =>
      urlOf(input).endsWith("/history") ? history.fetch(input, init) : hanging(input, init),
    );

    const sending = controller.send("Write an essay", null);
    await vi.waitFor(() => expect(controller.getSnapshot().conversation.live.text).toBe("Partial"));
    controller.openThread("t1");
    await sending;
    await vi.waitFor(() => expect(controller.getSnapshot().isLoadingHistory).toBe(false));

    const snapshot = controller.getSnapshot();
    expect(snapshot.threadId).toBe("t1");
    expect(snapshot.conversation.entries).toHaveLength(HISTORY_FIXTURES.toolCalls.messages.length);
    expect(snapshot.isRunning).toBe(false);
  });

  it("ignores events that still arrive after the user opened another thread", async () => {
    const encoder = new TextEncoder();
    let push: (frame: string) => void = () => undefined;
    const body = new ReadableStream<Uint8Array>({
      start(stream) {
        push = (frame) => stream.enqueue(encoder.encode(frame));
      },
    });
    const history = new FakeService({ histories: { t1: HISTORY_FIXTURES.toolCalls } });
    const { controller } = controllerFor((input, init) =>
      urlOf(input).endsWith("/history")
        ? history.fetch(input, init)
        : Promise.resolve(new Response(body, { headers: { "X-Thread-Id": "thread-old" } })),
    );

    void controller.send("Write an essay", null);
    push('data: {"type":"token","content":"Partial"}\n\n');
    await vi.waitFor(() => expect(controller.getSnapshot().conversation.live.text).toBe("Partial"));
    controller.openThread("t1");
    await vi.waitFor(() => expect(controller.getSnapshot().isLoadingHistory).toBe(false));
    push('data: {"type":"token","content":" late"}\n\n');
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(controller.getSnapshot().conversation.live.text).toBe("");
  });

  it("reports a thread that does not exist or belongs to someone else", async () => {
    const { controller } = controllerFor(new FakeService().fetch);

    controller.openThread("missing");
    await vi.waitFor(() => expect(controller.getSnapshot().isLoadingHistory).toBe(false));

    expect(controller.getSnapshot().historyError).toBe(THREAD_NOT_FOUND_MESSAGE);
  });

  it("explains when the service cannot be reached", async () => {
    const { controller } = controllerFor(() => Promise.reject(new TypeError("Failed to fetch")));

    await controller.send("Hi", null);

    const reply = toThreadMessages(controller.getSnapshot().conversation, false)[1];
    expect(reply?.status).toEqual({ type: "incomplete", reason: "error", error: UNREACHABLE_MESSAGE });
  });
});
