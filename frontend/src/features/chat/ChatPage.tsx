/**
 * Halaman chat untuk chat umum (`/`, `/chat/:threadId`, keputusan user F33) dan chat project
 * (`/projects/:projectId`, `/projects/:projectId/chat/:threadId`, F34).
 *
 * Route chat baru dan route thread memakai komponen ini di posisi yang sama, jadi state tetap utuh
 * saat URL chat baru diganti ke thread yang baru dibuat.
 */
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { useAuth } from "@/auth/auth-context";
import { Thread } from "@/components/assistant-ui/thread";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ModelPicker } from "@/features/chat/ModelPicker";
import { useChatRuntime } from "@/features/chat/use-chat-runtime";
import { chatPath, newChatPath, threadsQueryKey } from "@/features/threads/thread-paths";

export interface ChatPageProps {
  /** Project tempat chat berjalan, atau `null` untuk chat umum. */
  projectId?: string | null;
  /** Model default project, ditampilkan di pemilih model sebelum user memilih. */
  defaultModel?: string | null;
  /** Isi layar chat kosong. Default: sapaan untuk user. */
  welcome?: ReactNode;
}

export function ChatPage({ projectId = null, defaultModel = null, welcome }: ChatPageProps) {
  const { api, session } = useAuth();
  const { threadId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [model, setModel] = useState<string | null>(null);

  const refreshThreads = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: threadsQueryKey(projectId) });
  }, [queryClient, projectId]);
  const openCreatedThread = useCallback(
    (createdThreadId: string) => {
      refreshThreads();
      void navigate(chatPath(projectId, createdThreadId));
    },
    [navigate, projectId, refreshThreads],
  );
  const { runtime, snapshot } = useChatRuntime({
    api,
    projectId,
    threadId: threadId ?? null,
    model,
    onThreadCreated: openCreatedThread,
    onRunFinished: refreshThreads,
  });

  if (snapshot.historyError !== null) {
    return (
      <div className="mx-auto w-full max-w-xl p-6">
        <Alert variant="destructive">
          <AlertTitle>{snapshot.historyError}</AlertTitle>
          <AlertDescription>
            <Button asChild variant="link" className="h-auto p-0">
              <Link to={newChatPath(projectId)}>Start a new chat</Link>
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="min-h-0 flex-1">
        <Thread
          welcome={
            welcome ?? (
              <h1 className="text-2xl font-medium tracking-tight">Hello, {session?.username}</h1>
            )
          }
          composerExtra={
            <ModelPicker value={model} defaultModel={defaultModel} onChange={setModel} />
          }
        />
      </div>
    </AssistantRuntimeProvider>
  );
}
