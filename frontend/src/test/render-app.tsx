/**
 * Render seluruh aplikasi (route asli, auth, query) di memory router dengan service palsu.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

import { AuthProvider } from "@/auth/AuthProvider";
import { SessionStore } from "@/auth/session";
import { TooltipProvider } from "@/components/ui/tooltip";
import { appRoutes } from "@/routes/routes";
import type { FakeService } from "@/test/fake-service";

export function renderApp(service: FakeService, path = "/", store?: SessionStore) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const sessionStore = store ?? new SessionStore(window.sessionStorage);
  const view = render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider store={sessionStore} fetch={service.fetch}>
        <TooltipProvider>
          <RouterProvider router={router} />
        </TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
  return { ...view, router, sessionStore };
}
