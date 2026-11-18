/**
 * Hook TanStack Query untuk thread satu scope (chat umum atau satu project).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/auth/auth-context";
import { threadsQueryKey } from "@/features/threads/thread-paths";
import { ThreadsService } from "@/features/threads/threads-service";

/** Daftar thread terbaru di scope ini. */
export function useThreads(projectId: string | null) {
  const { api } = useAuth();
  return useQuery({
    queryKey: threadsQueryKey(projectId),
    queryFn: () => new ThreadsService(api, projectId).list(),
  });
}

export interface RenameThreadInput {
  threadId: string;
  title: string;
}

/** Rename thread, lalu muat ulang daftar thread scope ini. */
export function useRenameThread(projectId: string | null) {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ threadId, title }: RenameThreadInput) =>
      new ThreadsService(api, projectId).rename(threadId, title),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: threadsQueryKey(projectId) }),
  });
}

/** Hapus thread, lalu muat ulang daftar thread scope ini. */
export function useDeleteThread(projectId: string | null) {
  const { api } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (threadId: string) => new ThreadsService(api, projectId).remove(threadId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: threadsQueryKey(projectId) }),
  });
}
