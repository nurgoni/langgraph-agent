/**
 * Daftar, rename, dan hapus thread milik user, untuk chat umum (`/threads`) atau satu project
 * (`/projects/{project_id}/threads`).
 */
import type { ApiClient } from "@/api/client";
import type { components } from "@/api/schema";
import { requireData, requireOk } from "@/api/service-error";

export type ThreadSummary = components["schemas"]["ThreadSummary"];

/** Jumlah thread terbaru yang dimuat; batas maksimum `limit` di service. */
export const THREADS_LIMIT = 100;
const LIST_FAILED_MESSAGE = "Cannot load conversations.";
const RENAME_FAILED_MESSAGE = "Cannot rename this conversation.";
const DELETE_FAILED_MESSAGE = "Cannot delete this conversation.";

/**
 * Request thread untuk satu scope: chat umum atau satu project.
 *
 * Class karena setiap method memakai dependency yang sama (`api`, `projectId`).
 */
export class ThreadsService {
  private readonly api: ApiClient;
  private readonly projectId: string | null;

  /**
   * @param api Client bertipe ke agent service.
   * @param projectId Project, atau `null` untuk chat umum (agent default).
   */
  constructor(api: ApiClient, projectId: string | null) {
    this.api = api;
    this.projectId = projectId;
  }

  /**
   * Thread terbaru, yang terakhir di-update lebih dulu.
   *
   * @throws ServiceError Jika service menolak request atau tidak terjangkau.
   */
  async list(): Promise<ThreadSummary[]> {
    const query = { limit: THREADS_LIMIT };
    const projectId = this.projectId;
    const threads = await requireData(
      () =>
        projectId === null
          ? this.api.GET("/threads", { params: { query } })
          : this.api.GET("/projects/{project_id}/threads", {
              params: { path: { project_id: projectId }, query },
            }),
      LIST_FAILED_MESSAGE,
    );
    return threads.threads;
  }

  /**
   * Ganti judul thread.
   *
   * @throws ServiceError Jika judul ditolak (422), thread tidak ada (404), atau service tidak
   *   terjangkau.
   */
  async rename(threadId: string, title: string): Promise<ThreadSummary> {
    const body = { title };
    const projectId = this.projectId;
    return requireData(
      () =>
        projectId === null
          ? this.api.PATCH("/threads/{thread_id}", {
              params: { path: { thread_id: threadId } },
              body,
            })
          : this.api.PATCH("/projects/{project_id}/threads/{thread_id}", {
              params: { path: { project_id: projectId, thread_id: threadId } },
              body,
            }),
      RENAME_FAILED_MESSAGE,
    );
  }

  /**
   * Hapus thread beserta riwayatnya.
   *
   * @throws ServiceError Jika thread tidak ada (404) atau service tidak terjangkau.
   */
  async remove(threadId: string): Promise<void> {
    const projectId = this.projectId;
    await requireOk(
      () =>
        projectId === null
          ? this.api.DELETE("/threads/{thread_id}", { params: { path: { thread_id: threadId } } })
          : this.api.DELETE("/projects/{project_id}/threads/{thread_id}", {
              params: { path: { project_id: projectId, thread_id: threadId } },
            }),
      DELETE_FAILED_MESSAGE,
    );
  }
}
