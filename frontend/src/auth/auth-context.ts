/**
 * Konteks login: sesi saat ini, client API yang membawa token, serta aksi login dan logout.
 */
import { createContext, useContext } from "react";

import type { ApiClient } from "@/api/client";
import type { Session } from "@/auth/session";

export interface AuthContextValue {
  session: Session | null;
  api: ApiClient;
  /** Tukar username dan password dengan access token. Melempar `LoginError` jika gagal. */
  login: (username: string, password: string) => Promise<Session>;
  logout: () => void;
}

/** Login ditolak service (401/422) atau service tidak bisa dihubungi. */
export class LoginError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LoginError";
  }
}

export const AuthContext = createContext<AuthContextValue | null>(null);

/** Nilai konteks login. Harus dipakai di dalam `AuthProvider`. */
export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return value;
}
