/**
 * Halaman login (FR-42). Akun dibuat operator lewat CLI `manage create-user`, jadi tidak ada
 * halaman daftar.
 */
import { type FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { LoginError, useAuth } from "@/auth/auth-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { LoginRedirectState } from "@/routes/RequireAuth";

const HOME_PATH = "/";
const UNEXPECTED_ERROR_MESSAGE = "Something went wrong. Try again.";

export function LoginPage() {
  const { session, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const returnTo = redirectTarget(location.state);

  if (session !== null) {
    return <Navigate to={returnTo} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(username, password);
      await navigate(returnTo, { replace: true });
    } catch (caught) {
      setError(caught instanceof LoginError ? caught.message : UNEXPECTED_ERROR_MESSAGE);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-svh items-center justify-center bg-muted p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign in</CardTitle>
          <CardDescription>Use the account created by your administrator.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={(event) => void handleSubmit(event)}>
            <div className="grid gap-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoComplete="username"
                required
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
            {error !== null && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" disabled={submitting}>
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

/** Path asal dari state redirect `RequireAuth`, atau beranda. */
function redirectTarget(state: unknown): string {
  if (typeof state === "object" && state !== null && "from" in state) {
    const from = (state as LoginRedirectState).from;
    if (typeof from === "string" && from.startsWith(HOME_PATH)) {
      return from;
    }
  }
  return HOME_PATH;
}
