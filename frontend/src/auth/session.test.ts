import { describe, expect, it } from "vitest";

import { SESSION_STORAGE_KEY, SessionStore, type TokenResponse } from "@/auth/session";

const NOW = 1_800_000_000_000;
const TOKEN: TokenResponse = {
  access_token: "jwt",
  token_type: "bearer",
  expires_in: 60,
  user_id: "u1",
  username: "demo",
  role: "user",
};

function storeAt(now: number): SessionStore {
  return new SessionStore(window.sessionStorage, () => now);
}

describe("SessionStore", () => {
  it("saves the token with an absolute expiry and loads it back", () => {
    const saved = storeAt(NOW).save(TOKEN);

    expect(saved).toEqual({
      accessToken: "jwt",
      userId: "u1",
      username: "demo",
      role: "user",
      expiresAt: NOW + 60_000,
    });
    expect(storeAt(NOW + 59_999).load()).toEqual(saved);
  });

  it("treats an expired session as missing and removes it", () => {
    storeAt(NOW).save(TOKEN);

    expect(storeAt(NOW + 60_000).load()).toBeNull();
    expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
  });

  it.each(["not json", "{}", JSON.stringify({ accessToken: 1 }), "null"])(
    "drops a corrupt stored value %s",
    (raw) => {
      window.sessionStorage.setItem(SESSION_STORAGE_KEY, raw);

      expect(storeAt(NOW).load()).toBeNull();
      expect(window.sessionStorage.getItem(SESSION_STORAGE_KEY)).toBeNull();
    },
  );

  it("clears the session", () => {
    const store = storeAt(NOW);
    store.save(TOKEN);

    store.clear();

    expect(store.load()).toBeNull();
  });
});
