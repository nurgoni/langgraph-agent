/**
 * Penyedia konteks login. Sesi dibaca dari `SessionStore` saat mount, disimpan setelah login, dan
 * dihapus saat logout atau saat service menjawab 401 (token kedaluwarsa).
 */
import { type ReactNode, useCallback, useMemo, useState } from "react";

import { type ApiClient, createApiClient, errorDetail } from "@/api/client";
import { AuthContext, type AuthContextValue, LoginError } from "@/auth/auth-context";
import { type Session, SessionStore } from "@/auth/session";

const LOGIN_FAILED_MESSAGE = "Login failed. Check your username and password.";
const SERVICE_UNREACHABLE_MESSAGE = "Cannot reach the agent service. Try again later.";

interface AuthProviderProps {
  children: ReactNode;
  /** Penyimpanan sesi. Default: `sessionStorage` browser. */
  store?: SessionStore;
  /** Implementasi `fetch` untuk client API, bisa diganti di test. */
  fetch?: typeof globalThis.fetch;
}

export function AuthProvider({ children, store, fetch }: AuthProviderProps) {
  const [sessionStore] = useState(() => store ?? new SessionStore(window.sessionStorage));
  const [session, setSession] = useState<Session | null>(() => sessionStore.load());

  const logout = useCallback(() => {
    sessionStore.clear();
    setSession(null);
  }, [sessionStore]);

  const api = useMemo<ApiClient>(
    () =>
      createApiClient({
        // Store adalah sumber kebenaran, jadi token yang kedaluwarsa tidak pernah dikirim.
        getAccessToken: () => sessionStore.load()?.accessToken ?? null,
        onUnauthorized: logout,
        fetch,
      }),
    [sessionStore, fetch, logout],
  );

  const login = useCallback(
    async (username: string, password: string): Promise<Session> => {
      const token = await requestToken(api, username, password);
      const saved = sessionStore.save(token);
      setSession(saved);
      return saved;
    },
    [sessionStore, api],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ session, api, login, logout }),
    [session, api, login, logout],
  );
  return <AuthContext value={value}>{children}</AuthContext>;
}

async function requestToken(api: ApiClient, username: string, password: string) {
  let result;
  try {
    result = await api.POST("/auth/login", { body: { username, password } });
  } catch {
    throw new LoginError(SERVICE_UNREACHABLE_MESSAGE);
  }
  if (result.data === undefined) {
    throw new LoginError(errorDetail(result.error, LOGIN_FAILED_MESSAGE));
  }
  return result.data;
}
