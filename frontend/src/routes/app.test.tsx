/**
 * Acceptance F32 di jsdom: login di browser → app shell tampil, dengan route asli.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { SESSION_STORAGE_KEY, SessionStore } from "@/auth/session";
import { FakeService, VALID_PASSWORD } from "@/test/fake-service";
import { renderApp } from "@/test/render-app";

async function signIn(username: string, password: string) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Username"), username);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  return user;
}

describe("app", () => {
  it("sends anonymous visitors to the login page", async () => {
    const { router } = renderApp(new FakeService(), "/");

    expect(await screen.findByText("Sign in", { selector: "[data-slot=card-title]" }));
    expect(router.state.location.pathname).toBe("/login");
  });

  it("logs in and shows the app shell with live service info", async () => {
    const service = new FakeService();
    const { router } = renderApp(service, "/");

    await signIn("demo", VALID_PASSWORD);

    expect(await screen.findByRole("heading", { name: "Hello, demo" })).toBeInTheDocument();
    expect(screen.getByText("Recents")).toBeInTheDocument();
    expect(await screen.findByText("Connected · 2 agents · default chatbot")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
    expect(service.requests.map((request) => [request.path, request.authorization])).toEqual([
      ["/api/auth/login", null],
      ["/api/info", "Bearer token-for-demo"],
    ]);
    expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).toContain("token-for-demo");
  });

  it("shows the service error for wrong credentials", async () => {
    renderApp(new FakeService(), "/login");

    await signIn("demo", "wrong-password");

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
    expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });

  it("signs out back to the login page", async () => {
    renderApp(new FakeService(), "/");
    const user = await signIn("demo", VALID_PASSWORD);

    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByLabelText("Username")).toBeInTheDocument();
    expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });

  it("keeps a stored session across reloads until it expires", async () => {
    const now = Date.now();
    new SessionStore(window.sessionStorage, () => now).save({
      access_token: "stored",
      token_type: "bearer",
      expires_in: 60,
      user_id: "u1",
      username: "returning",
      role: "user",
    });

    renderApp(new FakeService(), "/");
    expect(await screen.findByRole("heading", { name: "Hello, returning" })).toBeInTheDocument();

    const expired = new SessionStore(window.sessionStorage, () => now + 61_000);
    renderApp(new FakeService(), "/", expired);
    expect(await screen.findByLabelText("Username")).toBeInTheDocument();
  });

  it("returns to login when the service rejects the token", async () => {
    renderApp(new FakeService({ rejectToken: true }), "/");

    await signIn("demo", VALID_PASSWORD);

    await waitFor(() => expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull());
    expect(await screen.findByLabelText("Username")).toBeInTheDocument();
  });
});
