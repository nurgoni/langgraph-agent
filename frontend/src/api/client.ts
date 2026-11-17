/**
 * Client API bertipe, dari kontrak service (`contracts/openapi.json`, F25).
 *
 * Tipe di `schema.d.ts` digenerate dengan `pnpm generate:api` dan tidak ditulis manual (FR-35).
 * Semua request lewat prefix same-origin `/api`, yang di-proxy ke service oleh nginx (image `web`)
 * atau Vite (dev), jadi browser tidak butuh CORS (keputusan user F32).
 */
import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "@/api/schema";

export const API_PATH = "/api";
const HTTP_UNAUTHORIZED = 401;

export type ApiClient = ReturnType<typeof createClient<paths>>;

export interface ApiClientOptions {
  /** Access token saat ini, dibaca di setiap request. */
  getAccessToken: () => string | null;
  /** Dipanggil saat service menjawab 401 untuk request yang membawa token. */
  onUnauthorized: () => void;
  /** Implementasi `fetch`, bisa diganti di test. */
  fetch?: typeof globalThis.fetch;
  /** Default: `<origin halaman>/api`, absolut supaya `Request` juga valid di luar browser. */
  baseUrl?: string;
}

/** Client dengan header `Authorization: Bearer` otomatis dan penanganan token kedaluwarsa. */
export function createApiClient(options: ApiClientOptions): ApiClient {
  const client = createClient<paths>({
    baseUrl: options.baseUrl ?? `${window.location.origin}${API_PATH}`,
    fetch: options.fetch,
  });
  client.use(authMiddleware(options));
  return client;
}

function authMiddleware(options: ApiClientOptions): Middleware {
  return {
    onRequest({ request }) {
      const token = options.getAccessToken();
      if (token !== null) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      return request;
    },
    onResponse({ request, response }) {
      if (response.status === HTTP_UNAUTHORIZED && request.headers.has("Authorization")) {
        options.onUnauthorized();
      }
      return response;
    },
  };
}

/** Pesan error yang bisa ditampilkan dari body error service (`{"detail": ...}`, NFR-6). */
export function errorDetail(error: unknown, fallback: string): string {
  if (typeof error !== "object" || error === null || !("detail" in error)) {
    return fallback;
  }
  const detail = error.detail;
  return typeof detail === "string" ? detail : fallback;
}
