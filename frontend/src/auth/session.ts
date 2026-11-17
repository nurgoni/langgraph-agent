/**
 * Penyimpanan sesi login di browser (keputusan user F32: `sessionStorage`).
 *
 * Token bertahan saat halaman di-refresh dan hilang saat tab ditutup. Service tidak punya refresh
 * token (F24), jadi sesi yang melewati `expiresAt` dianggap tidak ada.
 */
import type { components } from "@/api/schema";

export type TokenResponse = components["schemas"]["TokenResponse"];

export interface Session {
  accessToken: string;
  userId: string;
  username: string;
  role: TokenResponse["role"];
  /** Waktu kedaluwarsa token, milidetik sejak epoch. */
  expiresAt: number;
}

export const SESSION_STORAGE_KEY = "agent-service.session";
const MILLISECONDS_PER_SECOND = 1000;

export type Clock = () => number;

/** Sesi dari respons `POST /auth/login`, dengan waktu kedaluwarsa absolut. */
export function sessionFromToken(token: TokenResponse, now: number): Session {
  return {
    accessToken: token.access_token,
    userId: token.user_id,
    username: token.username,
    role: token.role,
    expiresAt: now + token.expires_in * MILLISECONDS_PER_SECOND,
  };
}

/** Membaca, menyimpan, dan menghapus sesi di satu `Storage`. */
export class SessionStore {
  private readonly storage: Storage;
  private readonly clock: Clock;

  constructor(storage: Storage, clock: Clock = Date.now) {
    this.storage = storage;
    this.clock = clock;
  }

  /** Sesi yang masih berlaku, atau `null` jika tidak ada, rusak, atau kedaluwarsa. */
  load(): Session | null {
    const raw = this.storage.getItem(SESSION_STORAGE_KEY);
    if (raw === null) {
      return null;
    }
    const session = parseSession(raw);
    if (session === null || session.expiresAt <= this.clock()) {
      this.clear();
      return null;
    }
    return session;
  }

  /** Simpan sesi dari token login, dan kembalikan sesi itu. */
  save(token: TokenResponse): Session {
    const session = sessionFromToken(token, this.clock());
    this.storage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
    return session;
  }

  clear(): void {
    this.storage.removeItem(SESSION_STORAGE_KEY);
  }
}

function parseSession(raw: string): Session | null {
  try {
    const value: unknown = JSON.parse(raw);
    return isSession(value) ? value : null;
  } catch {
    return null;
  }
}

function isSession(value: unknown): value is Session {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.accessToken === "string" &&
    typeof candidate.userId === "string" &&
    typeof candidate.username === "string" &&
    typeof candidate.expiresAt === "number"
  );
}
