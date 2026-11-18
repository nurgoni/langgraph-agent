/**
 * State panel preview artifact (FR-50): artifact yang sedang dibuka di panel kanan.
 */
import { createContext, useContext } from "react";

import type { ArtifactRef } from "@/features/artifacts/artifacts-service";

export interface ArtifactPanelState {
  /** Artifact yang sedang dipreview, atau `null` jika panel tertutup. */
  selected: ArtifactRef | null;
  open: (artifact: ArtifactRef) => void;
  close: () => void;
}

export const ArtifactPanelContext = createContext<ArtifactPanelState | null>(null);

/** State panel artifact dari `ArtifactPanelProvider` terdekat. */
export function useArtifactPanel(): ArtifactPanelState {
  const state = useContext(ArtifactPanelContext);
  if (state === null) {
    throw new Error("useArtifactPanel must be used inside ArtifactPanelProvider");
  }
  return state;
}
