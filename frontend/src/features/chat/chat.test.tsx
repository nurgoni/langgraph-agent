/**
 * Acceptance F33 di jsdom: chat setara Streamlit untuk FR-20, FR-23, FR-24, FR-29, dan FR-30,
 * dengan route asli dan rekaman SSE asli.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { SessionStore } from "@/auth/session";
import { TRUNCATED_WARNING } from "@/components/assistant-ui/thread";
import { FakeService, NEW_THREAD_ID } from "@/test/fake-service";
import { ERROR_SSE, HISTORY_FIXTURES, SSE_FIXTURES } from "@/test/fixtures";
import { renderApp } from "@/test/render-app";

const SUB_AGENTS_THREAD = "thread-sub-agents";
const TRUNCATED_THREAD = "thread-truncated";

beforeEach(() => {
  new SessionStore(window.sessionStorage).save({
    access_token: "jwt",
    token_type: "bearer",
    expires_in: 3600,
    user_id: "u1",
    username: "demo",
    role: "user",
  });
});

async function send(text: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Message input"), text);
  await user.click(screen.getByRole("button", { name: "Send message" }));
}

describe("chat", () => {
  it("greets the user on a new chat with the default model selected", async () => {
    renderApp(new FakeService(), "/");

    expect(await screen.findByRole("heading", { name: "Hello, demo" })).toBeInTheDocument();
    expect(await screen.findByRole("combobox", { name: "Model" })).toHaveTextContent("fake");
  });

  it("streams a reply and moves a new chat to its thread URL (FR-20, FR-29)", async () => {
    const service = new FakeService({ streams: [SSE_FIXTURES.reasoning] });
    const { router } = renderApp(service, "/");

    await send("Is 221 a prime number?");

    expect(await screen.findByText(/221 is not a prime number/)).toBeInTheDocument();
    expect(within(screen.getByRole("main")).getByText("Is 221 a prime number?")).toBeInTheDocument();
    const recents = await screen.findByRole("list", { name: "Recent chats" });
    expect(within(recents).getByRole("link", { name: "Is 221 a prime number?" })).toHaveAttribute(
      "href",
      `/chat/${NEW_THREAD_ID}`,
    );
    expect(screen.getByRole("button", { name: /Reasoning|Thought/ })).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.pathname).toBe(`/chat/${NEW_THREAD_ID}`));
    expect(service.requestsTo("/api/history")).toEqual([]);
    expect(service.requestsTo("/api/stream")[0]).toMatchObject({
      authorization: "Bearer jwt",
      body: { message: "Is 221 a prime number?", thread_id: null, stream_tokens: true },
    });
  });

  it("reopens a thread from the URL with sub-agent steps nested (FR-23)", async () => {
    const service = new FakeService({
      histories: { [SUB_AGENTS_THREAD]: HISTORY_FIXTURES.subAgents },
    });
    renderApp(service, `/chat/${SUB_AGENTS_THREAD}`);

    const expert = await screen.findByRole("region", { name: "Sub-agent math_expert" });
    expect(within(expert).getByText(/The result of/)).toBeInTheDocument();
    expect(within(expert).queryByText(/The answer is/)).toBeNull();
    expect(screen.getByText(/The answer is/)).toBeInTheDocument();
    expect(service.requestsTo("/api/history")[0]?.body).toEqual({ thread_id: SUB_AGENTS_THREAD });
  });

  it("continues the opened thread when the user replies", async () => {
    const service = new FakeService({
      histories: { [SUB_AGENTS_THREAD]: HISTORY_FIXTURES.subAgents },
      streams: [SSE_FIXTURES.interrupt],
    });
    renderApp(service, `/chat/${SUB_AGENTS_THREAD}`);
    await screen.findByRole("region", { name: "Sub-agent math_expert" });

    await send("Thanks");

    expect(await screen.findByText("What is your birthdate?")).toBeInTheDocument();
    expect(service.requestsTo("/api/stream")[0]?.body).toMatchObject({
      thread_id: SUB_AGENTS_THREAD,
    });
  });

  it("shows an interrupt question as a normal AI message (FR-24)", async () => {
    renderApp(new FakeService({ streams: [SSE_FIXTURES.interrupt] }), "/");

    await send("Hi");

    expect(await screen.findByText("What is your birthdate?")).toBeInTheDocument();
  });

  it("warns when the answer was cut off by the token limit (FR-30)", async () => {
    renderApp(
      new FakeService({ histories: { [TRUNCATED_THREAD]: HISTORY_FIXTURES.truncated } }),
      `/chat/${TRUNCATED_THREAD}`,
    );

    expect(await screen.findByRole("note")).toHaveTextContent(TRUNCATED_WARNING);
  });

  it("shows the error frame of a failed run", async () => {
    renderApp(new FakeService({ streams: [ERROR_SSE] }), "/");

    await send("Hi");

    expect(await screen.findByText("Model provider is unavailable")).toBeInTheDocument();
  });

  it("offers a new chat when the thread does not exist", async () => {
    const { router } = renderApp(new FakeService(), "/chat/missing");

    expect(await screen.findByText("This conversation was not found.")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("link", { name: "Start a new chat" }));

    expect(await screen.findByRole("heading", { name: "Hello, demo" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });
});
