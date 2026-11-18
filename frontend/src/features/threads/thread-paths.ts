/**
 * URL chat dan query key daftar thread, untuk chat umum dan chat di dalam project.
 *
 * Chat umum: `/` (baru) dan `/chat/:threadId` (keputusan user F33). Chat project:
 * `/projects/:projectId` (composer di halaman project) dan `/projects/:projectId/chat/:threadId`
 * (keputusan user F34).
 */

export const PROJECTS_PATH = "/projects";
export const NEW_PROJECT_PATH = "/projects/new";
const GENERAL_THREADS_KEY = "general";

/** URL chat baru: beranda untuk chat umum, halaman project untuk chat project. */
export function newChatPath(projectId: string | null): string {
  return projectId === null ? "/" : projectPath(projectId);
}

/** URL thread yang dibuka ulang. */
export function chatPath(projectId: string | null, threadId: string): string {
  const prefix = projectId === null ? "" : projectPath(projectId);
  return `${prefix}/chat/${encodeURIComponent(threadId)}`;
}

/** URL halaman project. */
export function projectPath(projectId: string): string {
  return `${PROJECTS_PATH}/${encodeURIComponent(projectId)}`;
}

/** URL form edit project. */
export function editProjectPath(projectId: string): string {
  return `${projectPath(projectId)}/edit`;
}

/** Query key daftar thread chat umum atau satu project. Prefix `["threads"]` untuk semua. */
export function threadsQueryKey(projectId: string | null): readonly string[] {
  return ["threads", projectId ?? GENERAL_THREADS_KEY];
}

export const ALL_THREADS_QUERY_KEY = ["threads"] as const;
