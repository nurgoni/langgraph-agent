/**
 * Recents di sidebar (FR-44): chat umum milik user, terbaru lebih dulu. Chat project tampil di
 * halaman project masing-masing (keputusan user F34).
 */
import { MoreHorizontal } from "lucide-react";
import { Link, useParams } from "react-router";

import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
} from "@/components/ui/sidebar";
import { ThreadActions } from "@/features/threads/ThreadActions";
import { chatPath } from "@/features/threads/thread-paths";
import { useThreads } from "@/features/threads/use-threads";

const SKELETON_ROWS = 3;

export function RecentsList() {
  const threads = useThreads(null);
  const { projectId, threadId: openThreadId } = useParams();
  const activeThreadId = projectId === undefined ? openThreadId : undefined;
  return (
    <SidebarGroup>
      <SidebarGroupLabel>Recents</SidebarGroupLabel>
      {threads.isPending && <RecentsSkeleton />}
      {threads.isError && (
        <p role="alert" className="px-2 text-sm text-destructive">
          {threads.error.message}
        </p>
      )}
      {threads.isSuccess && threads.data.length === 0 && (
        <p className="px-2 text-sm text-muted-foreground">No chats yet.</p>
      )}
      {threads.isSuccess && threads.data.length > 0 && (
        <SidebarMenu aria-label="Recent chats">
          {threads.data.map((thread) => (
            <SidebarMenuItem key={thread.thread_id}>
              <SidebarMenuButton asChild isActive={thread.thread_id === activeThreadId}>
                <Link to={chatPath(null, thread.thread_id)} title={thread.title}>
                  <span>{thread.title}</span>
                </Link>
              </SidebarMenuButton>
              <ThreadActions
                thread={thread}
                projectId={null}
                trigger={
                  <SidebarMenuAction showOnHover aria-label={`Actions for ${thread.title}`}>
                    <MoreHorizontal />
                  </SidebarMenuAction>
                }
              />
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      )}
    </SidebarGroup>
  );
}

function RecentsSkeleton() {
  const rows: number[] = [];
  for (let row = 0; row < SKELETON_ROWS; row += 1) {
    rows.push(row);
  }
  return (
    <SidebarMenu aria-busy="true">
      {rows.map((row) => (
        <SidebarMenuItem key={row}>
          <SidebarMenuSkeleton />
        </SidebarMenuItem>
      ))}
    </SidebarMenu>
  );
}
