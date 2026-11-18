/**
 * Panel preview artifact (FR-50): nama, ukuran, tombol unduh dan tutup, lalu isi preview.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Download, X } from "lucide-react";
import { useState } from "react";

import { useAuth } from "@/auth/auth-context";
import { Button } from "@/components/ui/button";
import { saveBlob } from "@/features/artifacts/artifact-download";
import { formatSize } from "@/features/artifacts/artifact-kind";
import { ArtifactPreview } from "@/features/artifacts/ArtifactPreview";
import { type ArtifactRef, ArtifactsService } from "@/features/artifacts/artifacts-service";
import type { ArtifactContent } from "@/features/artifacts/use-artifact-content";

export interface ArtifactPanelProps {
  artifact: ArtifactRef;
  onClose: () => void;
}

export function ArtifactPanel({ artifact, onClose }: ArtifactPanelProps) {
  const download = useDownload(artifact);
  return (
    <section aria-label={`Preview of ${artifact.name}`} className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 border-b px-4 py-2">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-medium" title={artifact.name}>
            {artifact.name}
          </h2>
          <p className="text-muted-foreground text-xs">
            {artifact.mime_type} · {formatSize(artifact.size)}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Download ${artifact.name}`}
          disabled={download.pending}
          onClick={() => void download.run()}
        >
          <Download />
        </Button>
        <Button variant="ghost" size="icon" aria-label="Close preview" onClick={onClose}>
          <X />
        </Button>
      </header>
      {download.error !== null && (
        <p role="alert" className="text-destructive px-4 pt-2 text-sm">
          {download.error}
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-auto p-4">
        <ArtifactPreview artifact={artifact} />
      </div>
    </section>
  );
}

/** Unduh isi artifact (dari cache preview jika sudah dimuat) lalu simpan sebagai file. */
function useDownload(artifact: ArtifactRef) {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setPending(true);
    setError(null);
    try {
      const cached = queryClient.getQueryData<ArtifactContent>(["artifact-content", artifact.id]);
      const blob = cached?.blob ?? (await new ArtifactsService(api).download(artifact.id));
      saveBlob(blob, artifact.name);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Cannot download this file.");
    } finally {
      setPending(false);
    }
  };
  return { pending, error, run };
}
