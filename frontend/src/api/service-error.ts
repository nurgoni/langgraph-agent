/**
 * Error request ke agent service untuk query dan mutation TanStack Query (projects, threads).
 */
import { errorDetail } from "@/api/client";

export const UNREACHABLE_MESSAGE = "Cannot reach the agent service. Try again later.";
export const HTTP_NOT_FOUND = 404;

/** Request gagal. `status` berisi kode HTTP, atau `null` jika service tidak terjangkau. */
export class ServiceError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null) {
    super(message);
    this.name = "ServiceError";
    this.status = status;
  }
}

/** Bentuk hasil `openapi-fetch` yang dibaca helper di modul ini. */
interface ServiceResult<D> {
  data?: D;
  error?: unknown;
  response: Response;
}

/**
 * Jalankan request dan kembalikan body sukses.
 *
 * @param request Request `openapi-fetch`.
 * @param fallback Pesan jika body error tidak berisi `detail`.
 * @throws ServiceError Jika service menjawab error atau tidak terjangkau.
 */
export async function requireData<D>(
  request: () => Promise<ServiceResult<D>>,
  fallback: string,
): Promise<D> {
  const result = await sendRequest(request);
  if (!result.response.ok || result.data === undefined) {
    throw new ServiceError(errorDetail(result.error, fallback), result.response.status);
  }
  return result.data;
}

/**
 * Jalankan request tanpa body sukses, misalnya `DELETE` yang menjawab 204.
 *
 * @throws ServiceError Jika service menjawab error atau tidak terjangkau.
 */
export async function requireOk(
  request: () => Promise<ServiceResult<unknown>>,
  fallback: string,
): Promise<void> {
  const result = await sendRequest(request);
  if (!result.response.ok) {
    throw new ServiceError(errorDetail(result.error, fallback), result.response.status);
  }
}

/** Kegagalan jaringan (`fetch` melempar `TypeError`) menjadi `ServiceError` tanpa status. */
async function sendRequest<R>(request: () => Promise<R>): Promise<R> {
  try {
    return await request();
  } catch (caught) {
    if (caught instanceof TypeError) {
      throw new ServiceError(UNREACHABLE_MESSAGE, null);
    }
    throw caught;
  }
}
