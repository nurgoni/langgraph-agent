/**
 * Request artifact ke agent service (FR-46): upload dari composer, unduh untuk preview, dan hapus
 * upload yang dibatalkan. Unduhan memakai token, jadi isi file dibaca sebagai `Blob` lalu
 * ditampilkan lewat object URL, bukan lewat link langsung.
 */
import type { ApiClient } from "@/api/client";
import type { components } from "@/api/schema";
import { requireData, requireOk } from "@/api/service-error";

export type ArtifactRef = components["schemas"]["ArtifactRef"];

const UPLOAD_FAILED_MESSAGE = "Cannot upload this file.";
const DOWNLOAD_FAILED_MESSAGE = "Cannot load this file.";
const DELETE_FAILED_MESSAGE = "Cannot remove this file.";
const UPLOAD_FIELD = "file";

/**
 * Upload, unduh, dan hapus artifact milik user.
 *
 * Class karena semua method memakai dependency yang sama (`api`). Semua method melempar
 * `ServiceError` jika service menolak request (misalnya 413 atau 404) atau tidak terjangkau.
 */
export class ArtifactsService {
  private readonly api: ApiClient;

  /** @param api Client bertipe ke agent service. */
  constructor(api: ApiClient) {
    this.api = api;
  }

  /** Upload satu file (`POST /artifacts`, multipart). */
  async upload(file: File): Promise<ArtifactRef> {
    const form = new FormData();
    form.append(UPLOAD_FIELD, file, file.name);
    return requireData(
      () =>
        this.api.POST("/artifacts", {
          // Body asli multipart; tipe hasil generate hanya menggambarkan field-nya.
          body: { file: file.name },
          bodySerializer: () => form,
        }),
      UPLOAD_FAILED_MESSAGE,
    );
  }

  /** Isi artifact sebagai `Blob` (`GET /artifacts/{id}`). */
  async download(artifactId: string): Promise<Blob> {
    return requireData(
      () =>
        this.api.GET("/artifacts/{artifact_id}", {
          params: { path: { artifact_id: artifactId } },
          parseAs: "blob",
        }),
      DOWNLOAD_FAILED_MESSAGE,
    );
  }

  /** Hapus artifact, misalnya upload yang dibatalkan dari composer. */
  async remove(artifactId: string): Promise<void> {
    await requireOk(
      () =>
        this.api.DELETE("/artifacts/{artifact_id}", {
          params: { path: { artifact_id: artifactId } },
        }),
      DELETE_FAILED_MESSAGE,
    );
  }
}
