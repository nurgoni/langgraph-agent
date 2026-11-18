/**
 * Layout chat + panel artifact (keputusan user F38): panel kanan yang lebarnya bisa ditarik
 * (shadcn `resizable`), atau Sheet penuh di layar sempit. Menyediakan `ArtifactPanelContext`.
 */
import { type ReactNode, useMemo, useState } from "react";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { ArtifactPanel } from "@/features/artifacts/ArtifactPanel";
import {
  ArtifactPanelContext,
  type ArtifactPanelState,
} from "@/features/artifacts/artifact-panel-context";
import type { ArtifactRef } from "@/features/artifacts/artifacts-service";
import { useIsMobile } from "@/hooks/use-mobile";

const CHAT_DEFAULT_SIZE = "55%";
const PANEL_DEFAULT_SIZE = "45%";
const MIN_SIZE = "25%";

export function ArtifactWorkspace({ children }: { children: ReactNode }) {
  const [selected, setSelected] = useState<ArtifactRef | null>(null);
  const isMobile = useIsMobile();
  const state = useMemo<ArtifactPanelState>(
    () => ({ selected, open: setSelected, close: () => setSelected(null) }),
    [selected],
  );
  return (
    <ArtifactPanelContext.Provider value={state}>
      {selected !== null && isMobile && (
        <Sheet open onOpenChange={(open) => !open && state.close()}>
          <SheetContent side="right" className="w-full p-0 sm:max-w-full">
            <SheetTitle className="sr-only">{selected.name}</SheetTitle>
            <ArtifactPanel artifact={selected} onClose={state.close} />
          </SheetContent>
        </Sheet>
      )}
      {/* Grup selalu dirender supaya chat tidak di-mount ulang saat panel dibuka atau ditutup. */}
      <ResizablePanelGroup orientation="horizontal" className="min-h-0 flex-1">
        <ResizablePanel
          id="chat"
          defaultSize={CHAT_DEFAULT_SIZE}
          minSize={MIN_SIZE}
          className="flex min-h-0 flex-col"
        >
          {children}
        </ResizablePanel>
        {selected !== null && !isMobile && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel id="artifact" defaultSize={PANEL_DEFAULT_SIZE} minSize={MIN_SIZE}>
              <ArtifactPanel key={selected.id} artifact={selected} onClose={state.close} />
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>
    </ArtifactPanelContext.Provider>
  );
}
