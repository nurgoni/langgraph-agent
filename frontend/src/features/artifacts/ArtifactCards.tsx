/**
 * Kartu artifact di pesan (FR-50): file yang dilampirkan user dan file yang dibagikan agent.
 * Klik kartu membuka panel preview.
 */
import { File, FileImage, FileSpreadsheet, FileText } from "lucide-react";
import type { ComponentType } from "react";

import { Button } from "@/components/ui/button";
import { type ArtifactKind, artifactKind, formatSize } from "@/features/artifacts/artifact-kind";
import { useArtifactPanel } from "@/features/artifacts/artifact-panel-context";
import type { ArtifactRef } from "@/features/artifacts/artifacts-service";

const KIND_ICONS: Record<ArtifactKind, ComponentType> = {
  image: FileImage,
  csv: FileSpreadsheet,
  pdf: FileText,
  text: FileText,
  other: File,
};

export function ArtifactCards({ artifacts }: { artifacts: readonly ArtifactRef[] }) {
  const panel = useArtifactPanel();
  if (artifacts.length === 0) {
    return null;
  }
  return (
    <ul className="my-2 flex flex-wrap gap-2" aria-label="Files">
      {artifacts.map((artifact) => {
        const Icon = KIND_ICONS[artifactKind(artifact)];
        const active = panel.selected?.id === artifact.id;
        return (
          <li key={artifact.id}>
            <Button
              variant={active ? "secondary" : "outline"}
              className="h-auto max-w-64 justify-start gap-2 py-1.5 text-left"
              aria-label={`Open ${artifact.name}`}
              onClick={() => panel.open(artifact)}
            >
              <Icon />
              <span className="grid min-w-0">
                <span className="truncate text-sm">{artifact.name}</span>
                <span className="text-muted-foreground text-xs">{formatSize(artifact.size)}</span>
              </span>
            </Button>
          </li>
        );
      })}
    </ul>
  );
}
