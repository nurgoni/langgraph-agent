/**
 * Route induk yang hanya bisa dibuka setelah login. Tanpa sesi, user diarahkan ke `/login`, dan
 * path asalnya dibawa di state supaya bisa kembali setelah login.
 */
import { Navigate, Outlet, useLocation } from "react-router";

import { useAuth } from "@/auth/auth-context";

export interface LoginRedirectState {
  from: string;
}

export function RequireAuth() {
  const { session } = useAuth();
  const location = useLocation();
  if (session === null) {
    const state: LoginRedirectState = { from: location.pathname };
    return <Navigate to="/login" replace state={state} />;
  }
  return <Outlet />;
}
