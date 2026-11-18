/**
 * Acceptance F34 (FR-44) di jsdom: Recents di sidebar dengan rename dan hapus.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import type { components } from "@/api/schema";
import { DEFAULT_AGENT, FakeService } from "@/test/fake-service";
import { HISTORY_FIXTURES } from "@/test/fixtures";
import { renderApp, saveSession } from "@/test/render-app";

type ThreadSummary = components["schemas"]["ThreadSummary"];

function thread(threadId: string, title: string): ThreadSummary {
  return { thread_id: threadId, agent_id: DEFAULT_AGENT, project_id: null, title };
}

const GENERAL_THREADS = [thread("t1", "Prime numbers"), thread("t2", "Trip plan")];

beforeEach(() => saveSession());

async function openThreadMenu(title: string) {
  const user = userEvent.setup();
  const recents = await screen.findByRole("list", { name: "Recent chats" });
  await user.click(within(recents).getByRole("button", { name: `Actions for ${title}` }));
  return user;
}

describe("recents", () => {
  it("lists the user's general chats, newest first", async () => {
    renderApp(new FakeService({ threads: { general: GENERAL_THREADS } }), "/");

    const recents = await screen.findByRole("list", { name: "Recent chats" });
    const links = within(recents).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["Prime numbers", "Trip plan"]);
    expect(links[0]).toHaveAttribute("href", "/chat/t1");
  });

  it("renames a chat through the dialog", async () => {
    const service = new FakeService({ threads: { general: GENERAL_THREADS } });
    renderApp(service, "/");

    const user = await openThreadMenu("Trip plan");
    await user.click(await screen.findByRole("menuitem", { name: "Rename" }));
    const title = await screen.findByRole("textbox", { name: "Title" });
    await user.clear(title);
    await user.type(title, "Bali trip");
    await user.click(screen.getByRole("button", { name: "Save" }));

    const recents = screen.getByRole("list", { name: "Recent chats" });
    expect(await within(recents).findByRole("link", { name: "Bali trip" })).toBeInTheDocument();
    expect(service.requestsTo("/api/threads/t2", "PATCH")[0]?.body).toEqual({ title: "Bali trip" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does not send an empty title", async () => {
    const service = new FakeService({ threads: { general: GENERAL_THREADS } });
    renderApp(service, "/");

    const user = await openThreadMenu("Trip plan");
    await user.click(await screen.findByRole("menuitem", { name: "Rename" }));
    await user.clear(await screen.findByRole("textbox", { name: "Title" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Enter a title.")).toBeInTheDocument();
    expect(service.requestsTo("/api/threads/t2", "PATCH")).toEqual([]);
  });

  it("deletes the open chat and returns to a new chat", async () => {
    const service = new FakeService({
      threads: { general: GENERAL_THREADS },
      histories: { t1: HISTORY_FIXTURES.toolCalls },
    });
    const { router } = renderApp(service, "/chat/t1");

    const user = await openThreadMenu("Prime numbers");
    await user.click(await screen.findByRole("menuitem", { name: "Delete" }));
    const confirm = await screen.findByRole("alertdialog");
    await user.click(within(confirm).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    expect(service.requestsTo("/api/threads/t1", "DELETE")).toHaveLength(1);
    const recents = screen.getByRole("list", { name: "Recent chats" });
    await waitFor(() => expect(within(recents).queryByText("Prime numbers")).toBeNull());
    expect(within(recents).getByText("Trip plan")).toBeInTheDocument();
  });
});
