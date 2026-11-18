/**
 * Layout utama setelah login (FR-42, FR-44): sidebar ala Claude (chat baru, Projects, Recents) dan
 * area konten.
 */
import { FolderOpen, LogOut, MessageSquarePlus } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router";

import { useAuth } from "@/auth/auth-context";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { RecentsList } from "@/features/threads/RecentsList";
import { PROJECTS_PATH } from "@/features/threads/thread-paths";

export const APP_NAME = "Agent Service";

export function AppShell() {
  const { session, logout } = useAuth();
  const { pathname } = useLocation();
  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader>
          <span className="px-2 text-sm font-semibold">{APP_NAME}</span>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton asChild>
                <Link to="/">
                  <MessageSquarePlus />
                  <span>New chat</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
            <SidebarMenuItem>
              <SidebarMenuButton asChild isActive={pathname.startsWith(PROJECTS_PATH)}>
                <Link to={PROJECTS_PATH}>
                  <FolderOpen />
                  <span>Projects</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          <RecentsList />
        </SidebarContent>
        <SidebarFooter>
          <div className="flex items-center justify-between gap-2 px-2">
            <span className="truncate text-sm" title={session?.username}>
              {session?.username}
            </span>
            <Button variant="ghost" size="icon" aria-label="Sign out" onClick={logout}>
              <LogOut />
            </Button>
          </div>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset className="h-svh">
        <header className="flex h-12 items-center border-b px-2">
          <SidebarTrigger />
        </header>
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  );
}
