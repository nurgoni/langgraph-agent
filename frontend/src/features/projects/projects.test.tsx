/**
 * Acceptance F34 (FR-44, FR-36, FR-38) di jsdom: halaman Projects, buat dan edit project dengan
 * skill, chat di dalam project, dan project built-in yang read-only.
 */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { BUILTIN_PROJECT, FakeService, NEW_THREAD_ID } from "@/test/fake-service";
import { SSE_FIXTURES } from "@/test/fixtures";
import { renderApp, saveSession } from "@/test/render-app";

const CREATED_PROJECT_ID = "project-1";

beforeEach(() => saveSession());

async function createProject(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByRole("textbox", { name: "Name" }), "Weekly notes");
  await user.type(
    screen.getByRole("textbox", { name: "Instructions" }),
    "Answer in bullet points.",
  );
  await user.click(await screen.findByRole("checkbox", { name: "meeting-notes" }));
  await user.click(screen.getByRole("button", { name: "Create project" }));
}

describe("projects", () => {
  it("lists projects with built-in ones marked (FR-44)", async () => {
    renderApp(new FakeService(), "/");

    await userEvent.setup().click(await screen.findByRole("link", { name: "Projects" }));

    const list = await screen.findByRole("list", { name: "Projects" });
    const card = within(list).getByRole("link", { name: /Research/ });
    expect(card).toHaveAttribute("href", `/projects/${BUILTIN_PROJECT.id}`);
    expect(within(card).getByText("Built-in")).toBeInTheDocument();
  });

  it("creates a project with instructions and a skill, chats in it, and lists the chat there", async () => {
    const service = new FakeService({ streams: [SSE_FIXTURES.reasoning] });
    const { router } = renderApp(service, "/projects/new");
    const user = userEvent.setup();

    await createProject(user);

    await waitFor(() =>
      expect(router.state.location.pathname).toBe(`/projects/${CREATED_PROJECT_ID}`),
    );
    expect(service.requestsTo("/api/projects", "POST")[0]?.body).toEqual({
      name: "Weekly notes",
      description: "",
      base_agent_id: "chatbot",
      model: null,
      instructions: "Answer in bullet points.",
      skill_ids: ["builtin/meeting-notes"],
      settings: { max_tokens: null },
    });
    expect(await screen.findByRole("heading", { name: "Weekly notes" })).toBeInTheDocument();
    expect(screen.getByText("Answer in bullet points.")).toBeInTheDocument();
    expect(screen.getByText("builtin/meeting-notes")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Message input"), "Is 221 a prime number?");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    expect(await screen.findByText(/221 is not a prime number/)).toBeInTheDocument();
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        `/projects/${CREATED_PROJECT_ID}/chat/${NEW_THREAD_ID}`,
      ),
    );
    expect(service.requestsTo(`/api/projects/${CREATED_PROJECT_ID}/stream`)).toHaveLength(1);
    expect(service.requestsTo("/api/stream")).toEqual([]);

    await user.click(screen.getByRole("link", { name: "Weekly notes" }));

    const chats = await screen.findByRole("region", { name: "Chats in this project" });
    expect(
      await within(chats).findByRole("link", { name: "Is 221 a prime number?" }),
    ).toHaveAttribute("href", `/projects/${CREATED_PROJECT_ID}/chat/${NEW_THREAD_ID}`);
    expect(screen.queryByRole("list", { name: "Recent chats" })).toBeNull();
  });

  it("shows field errors before sending an invalid project", async () => {
    const service = new FakeService();
    renderApp(service, "/projects/new");
    const user = userEvent.setup();

    await user.type(await screen.findByRole("textbox", { name: "Answer token limit" }), "0");
    await user.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByText("Enter a name.")).toBeInTheDocument();
    expect(screen.getByText("Use at least 1.")).toBeInTheDocument();
    expect(service.requestsTo("/api/projects", "POST")).toEqual([]);
  });

  it("edits a project without changing its agent", async () => {
    const service = new FakeService();
    const { router } = renderApp(service, "/projects/new");
    const user = userEvent.setup();
    await createProject(user);
    await screen.findByRole("heading", { name: "Weekly notes" });

    await user.click(screen.getByRole("button", { name: "Project actions" }));
    await user.click(await screen.findByRole("menuitem", { name: "Edit project" }));
    const name = await screen.findByRole("textbox", { name: "Name" });
    expect(name).toHaveValue("Weekly notes");
    expect(screen.getByRole("combobox", { name: "Agent" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "research-report" }));
    await user.clear(name);
    await user.type(name, "Team notes");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("heading", { name: "Team notes" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe(`/projects/${CREATED_PROJECT_ID}`);
    const update = service.requestsTo(`/api/projects/${CREATED_PROJECT_ID}`, "PATCH")[0];
    expect(update?.body).toMatchObject({
      name: "Team notes",
      skill_ids: ["builtin/meeting-notes", "builtin/research-report"],
    });
    expect(update?.body).not.toHaveProperty("base_agent_id");
  });

  it("deletes a project after confirmation", async () => {
    const service = new FakeService();
    const { router } = renderApp(service, "/projects/new");
    const user = userEvent.setup();
    await createProject(user);
    await screen.findByRole("heading", { name: "Weekly notes" });

    await user.click(screen.getByRole("button", { name: "Project actions" }));
    await user.click(await screen.findByRole("menuitem", { name: "Delete project" }));
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Delete" }),
    );

    await waitFor(() => expect(router.state.location.pathname).toBe("/projects"));
    const list = await screen.findByRole("list", { name: "Projects" });
    expect(within(list).queryByText("Weekly notes")).toBeNull();
    expect(service.requestsTo(`/api/projects/${CREATED_PROJECT_ID}`, "DELETE")).toHaveLength(1);
  });

  it("shows built-in projects read-only but lets the user chat in them", async () => {
    renderApp(new FakeService(), `/projects/${BUILTIN_PROJECT.id}`);

    expect(await screen.findByRole("heading", { name: "Research" })).toBeInTheDocument();
    expect(screen.getByText("Built-in")).toBeInTheDocument();
    expect(screen.getByText("Cite every source.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Project actions" })).toBeNull();
    expect(screen.getByLabelText("Message input")).toBeInTheDocument();
  });

  it("refuses to edit a built-in project", async () => {
    const service = new FakeService();
    renderApp(service, `/projects/${BUILTIN_PROJECT.id}/edit`);

    expect(await screen.findByText("Built-in projects are read-only.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Name" })).toBeNull();
  });

  it("reports a project that does not exist", async () => {
    renderApp(new FakeService(), "/projects/missing");

    expect(await screen.findByText("This project was not found.")).toBeInTheDocument();
  });
});
