import { describe, expect, it, vi } from "vitest";

import { createApiClient, errorDetail } from "@/api/client";
import { FakeService, VALID_PASSWORD } from "@/test/fake-service";

function client(service: FakeService, token: string | null, onUnauthorized = vi.fn()) {
  const api = createApiClient({
    getAccessToken: () => token,
    onUnauthorized,
    fetch: service.fetch,
    baseUrl: "http://web.test/api",
  });
  return { api, onUnauthorized };
}

describe("createApiClient", () => {
  it("sends the access token as a bearer header through the /api prefix", async () => {
    const service = new FakeService();
    const { api } = client(service, "jwt");

    const { data } = await api.GET("/info");

    expect(data?.default_agent).toBe("chatbot");
    expect(service.requests).toEqual([
      { method: "GET", path: "/api/info", authorization: "Bearer jwt" },
    ]);
  });

  it("reports 401 for authenticated requests only", async () => {
    const rejecting = client(new FakeService({ rejectToken: true }), "jwt");
    const anonymous = client(new FakeService(), null);

    await rejecting.api.GET("/info");
    const login = await anonymous.api.POST("/auth/login", {
      body: { username: "demo", password: "wrong" },
    });

    expect(rejecting.onUnauthorized).toHaveBeenCalledOnce();
    expect(anonymous.onUnauthorized).not.toHaveBeenCalled();
    expect(errorDetail(login.error, "fallback")).toBe("Invalid username or password");
  });

  it("logs in without a token", async () => {
    const service = new FakeService();
    const { api } = client(service, null);

    const { data } = await api.POST("/auth/login", {
      body: { username: "demo", password: VALID_PASSWORD },
    });

    expect(data?.access_token).toBe("token-for-demo");
    expect(service.requests[0]?.authorization).toBeNull();
  });
});

describe("errorDetail", () => {
  it.each([
    [{ detail: "Nope" }, "Nope"],
    [{ detail: [{ msg: "field" }] }, "fallback"],
    [null, "fallback"],
    ["text", "fallback"],
  ])("reads %j", (error, expected) => {
    expect(errorDetail(error, "fallback")).toBe(expected);
  });
});
