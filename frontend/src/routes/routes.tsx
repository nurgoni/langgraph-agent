/**
 * Daftar route aplikasi (mode data React Router). Dipakai `createBrowserRouter` di `main.tsx` dan
 * `createMemoryRouter` di test.
 */
import { Navigate, type RouteObject } from "react-router";

import { AppShell } from "@/routes/AppShell";
import { HomePage } from "@/routes/HomePage";
import { LoginPage } from "@/routes/LoginPage";
import { RequireAuth } from "@/routes/RequireAuth";

export const appRoutes: RouteObject[] = [
  { path: "/login", Component: LoginPage },
  {
    Component: RequireAuth,
    children: [
      {
        Component: AppShell,
        children: [{ index: true, Component: HomePage }],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
];
