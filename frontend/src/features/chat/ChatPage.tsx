/**
 * Halaman chat: `/` untuk chat baru dan `/chat/:threadId` untuk thread yang dibuka ulang
 * (keputusan user F33). Kedua route memakai komponen ini, jadi state tetap utuh saat URL chat baru
 * diganti ke thread yang baru dibuat.
 */
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { useAuth } from "@/auth/auth-context";
import { Thread } from "@/components/assistant-ui/thread";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { ModelPicker } from "@/features/chat/ModelPicker";
import { useChatRuntime } from "@/features/chat/use-chat-runtime";

export const CHAT_PATH_PREFIX = "/chat/";

export function ChatPage() {
  const { api, session } = useAuth();
  const { threadId } = useParams();
  const navigate = useNavigate();
  const [model, setModel] = useState<string | null>(null);
  const { runtime, snapshot } = useChatRuntime({
    api,
    threadId: threadId ?? null,
    model,
    onThreadCreated: (createdThreadId) => void navigate(`${CHAT_PATH_PREFIX}${createdThreadId}`),
  });

  if (snapshot.historyError !== null) {
    return (
      <div className="mx-auto w-full max-w-xl p-6">
        <Alert variant="destructive">
          <AlertTitle>{snapshot.historyError}</AlertTitle>
          <AlertDescription>
            <Button asChild variant="link" className="h-auto p-0">
              <Link to="/">Start a new chat</Link>
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
            <h1 className="text-2xl font-medium tracking-tight">Hello, {session?.username}</h1>
          }
          composerExtra={<ModelPicker value={model} onChange={setModel} />}
        />
      </div>
    </AssistantRuntimeProvider>
  );
}
