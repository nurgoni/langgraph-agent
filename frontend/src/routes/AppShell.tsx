/**
 * Layout utama setelah login (FR-42): sidebar ala Claude (chat baru, Recents) dan area konten.
 * Isi sidebar (thread, Projects) diisi F33/F34; di F32 sidebar masih kosong.
 */
import { LogOut, MessageSquarePlus } from "lucide-react";
import { Outlet } from "react-router";

import { useAuth } from "@/auth/auth-context";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";

export const APP_NAME = "Agent Service";

export function AppShell() {
  const { session, logout } = useAuth();
  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader>
          <span className="px-2 text-sm font-semibold">{APP_NAME}</span>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton disabled>
                <MessageSquarePlus />
                <span>New chat</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Recents</SidebarGroupLabel>
            <p className="px-2 text-sm text-muted-foreground">No chats yet.</p>
          </SidebarGroup>
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
      <SidebarInset>
        <header className="flex h-12 items-center border-b px-2">
          <SidebarTrigger />
        </header>
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  );
}
