/**
 * `AttachmentAdapter` assistant-ui untuk composer (FR-50, keputusan user F38): file di-upload ke
 * `POST /artifacts` saat dipilih, sehingga error ukuran (413) terlihat sebelum pesan dikirim.
 * Menghapus chip menghapus artifact-nya, dan pesan yang dikirim membawa ID artifact sebagai
 * `artifact_ids`.
 */
import type {
  Attachment,
  AttachmentAdapter,
  CompleteAttachment,
  PendingAttachment,
} from "@assistant-ui/react";

import type { ArtifactRef, ArtifactsService } from "@/features/artifacts/artifacts-service";

const ACCEPT_ANY_FILE = "*";
const UPLOAD_FAILED_MESSAGE = "Upload failed";
const IMAGE_MIME_PREFIX = "image/";

/**
 * Class karena menyimpan state yang berubah: artifact hasil upload per chip, sampai pesan dikirim.
 */
export class ArtifactAttachmentAdapter implements AttachmentAdapter {
  readonly accept = ACCEPT_ANY_FILE;
  private readonly service: ArtifactsService;
  private readonly uploaded = new Map<string, ArtifactRef>();

  /** @param service Client artifact. */
  constructor(service: ArtifactsService) {
    this.service = service;
  }

  /** Upload file yang dipilih, sambil melaporkan status ke chip composer. */
  async *add({ file }: { file: File }): AsyncGenerator<PendingAttachment, void> {
    const pending = {
      id: crypto.randomUUID(),
      type: file.type.startsWith(IMAGE_MIME_PREFIX) ? "image" : "file",
      name: file.name,
      contentType: file.type || undefined,
      file,
    } satisfies Omit<PendingAttachment, "status">;
    yield { ...pending, status: { type: "running", reason: "uploading", progress: 0 } };
    try {
      this.uploaded.set(pending.id, await this.service.upload(file));
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : UPLOAD_FAILED_MESSAGE;
      yield { ...pending, status: { type: "incomplete", reason: "error", message } };
      return;
    }
    yield { ...pending, status: { type: "requires-action", reason: "composer-send" } };
  }

  /** Hapus artifact milik chip yang dibuang dari composer. */
  async remove(attachment: Attachment): Promise<void> {
    const artifact = this.uploaded.get(attachment.id);
    this.uploaded.delete(attachment.id);
    if (artifact === undefined) {
      return;
    }
    try {
      await this.service.remove(artifact.id);
    } catch (caught) {
      // Upload yang gagal dihapus tidak tertaut ke thread mana pun; cukup dicatat.
      console.warn("Removing an attachment failed", caught);
    }
  }

  /**
   * Tandai lampiran siap dikirim.
   *
   * @throws Error Jika upload file ini belum berhasil.
   */
  send(attachment: PendingAttachment): Promise<CompleteAttachment> {
    if (!this.uploaded.has(attachment.id)) {
      return Promise.reject(new Error(`${attachment.name} was not uploaded`));
    }
    return Promise.resolve({ ...attachment, status: { type: "complete" }, content: [] });
  }

  /** Artifact hasil upload untuk lampiran pesan yang dikirim, urut sesuai lampiran. */
  takeArtifacts(attachmentIds: readonly string[]): ArtifactRef[] {
    const artifacts: ArtifactRef[] = [];
    for (const id of attachmentIds) {
      const artifact = this.uploaded.get(id);
      if (artifact !== undefined) {
        artifacts.push(artifact);
        this.uploaded.delete(id);
      }
    }
    return artifacts;
  }
}
