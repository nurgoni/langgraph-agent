/**
 * Artifact yang dibawa satu message assistant-ui: part `data` (jawaban asisten) atau
 * `metadata.custom` (pesan user). Lihat `ARTIFACTS_DATA_PART_NAME` di `conversation.ts`.
 */
import type { ArtifactRef } from "@/features/artifacts/artifacts-service";
import { ARTIFACTS_DATA_PART_NAME } from "@/features/chat/conversation";

interface DataLikePart {
  type: string;
  name?: string;
  data?: unknown;
}

/** Cek bentuk `ArtifactRef` dari data yang tidak bertipe. */
export function isArtifactRef(value: unknown): value is ArtifactRef {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.name === "string" &&
    typeof candidate.mime_type === "string" &&
    typeof candidate.size === "number"
  );
}

/** Artifact dari isi part `data` bernama `artifacts`, urut kemunculan. */
export function artifactsFromParts(parts: readonly DataLikePart[]): ArtifactRef[] {
  const artifacts: ArtifactRef[] = [];
  for (const part of parts) {
    if (part.type === "data" && part.name === ARTIFACTS_DATA_PART_NAME) {
      artifacts.push(...artifactsFromValue(part.data));
    }
  }
  return artifacts;
}

/** Artifact dari nilai tidak bertipe (isi part `data` atau `metadata.custom`). */
export function artifactsFromValue(value: unknown): ArtifactRef[] {
  return Array.isArray(value) ? value.filter(isArtifactRef) : [];
}
