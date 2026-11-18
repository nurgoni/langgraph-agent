/**
 * Runtime assistant-ui untuk agent service: `useExternalStoreRuntime` di atas `ChatController`.
 */
import {
  type AppendMessage,
  type AssistantRuntime,
  type ThreadMessageLike,
  useExternalStoreRuntime,
} from "@assistant-ui/react";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import type { ApiClient } from "@/api/client";
import { ArtifactsService } from "@/features/artifacts/artifacts-service";
import { ArtifactAttachmentAdapter } from "@/features/artifacts/attachment-adapter";
import { ChatController, type ChatSnapshot } from "@/features/chat/chat-controller";
import { ChatService } from "@/features/chat/chat-service";
import { toThreadMessages } from "@/features/chat/conversation";

export interface ChatRuntimeOptions {
  api: ApiClient;
  /**
   * Project tempat chat berjalan, atau `null` untuk chat umum. Dibaca sekali saat mount; halaman
   * memberi `key` per project supaya pindah project membuat controller baru.
   */
  projectId: string | null;
  /** Thread dari URL, atau `null` untuk chat baru. */
  threadId: string | null;
  /** Model pilihan user, atau `null` untuk default project atau service. */
  model: string | null;
  /** Dipanggil saat run pertama chat baru membuat thread. */
  onThreadCreated: (threadId: string) => void;
  /** Dipanggil setiap run berakhir. */
  onRunFinished: () => void;
}

export interface ChatRuntime {
  runtime: AssistantRuntime;
  snapshot: ChatSnapshot;
}

/** Message dari `ChatController` sudah berbentuk `ThreadMessageLike`. */
const identity = (message: ThreadMessageLike): ThreadMessageLike => message;

export function useChatRuntime(options: ChatRuntimeOptions): ChatRuntime {
  const { api, projectId, threadId, model, onThreadCreated, onRunFinished } = options;
  const [controller] = useState(() => new ChatController(new ChatService(api, projectId)));
  const [attachments] = useState(() => new ArtifactAttachmentAdapter(new ArtifactsService(api)));
  useEffect(() => {
    controller.setRunListeners({ onThreadCreated, onRunFinished });
  }, [controller, onThreadCreated, onRunFinished]);
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot);

  useEffect(() => {
    controller.openThread(threadId);
  }, [controller, threadId]);
  useEffect(() => () => controller.dispose(), [controller]);

  const messages = useMemo(
    () => toThreadMessages(snapshot.conversation, snapshot.isRunning),
    [snapshot.conversation, snapshot.isRunning],
  );
  const runtime = useExternalStoreRuntime({
    messages,
    convertMessage: identity,
    isRunning: snapshot.isRunning,
    isLoading: snapshot.isLoadingHistory,
    isDisabled: snapshot.historyError !== null,
    onNew: (message: AppendMessage) => {
      const attachmentIds = (message.attachments ?? []).map((attachment) => attachment.id);
      const artifacts = attachments.takeArtifacts(attachmentIds);
      return controller.send(messageText(message), model, artifacts);
    },
    onCancel: () => Promise.resolve(controller.cancel()),
    adapters: { attachments },
  });
  return { runtime, snapshot };
}

/** Gabungan part teks dari pesan yang dikirim composer. */
function messageText(message: AppendMessage): string {
  const texts: string[] = [];
  for (const part of message.content) {
    if (part.type === "text") {
      texts.push(part.text);
    }
  }
  return texts.join("\n");
}
