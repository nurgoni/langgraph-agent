/**
 * Beranda setelah login. Chat dibangun di F33; di F32 halaman ini membuktikan request
 * terautentikasi sampai ke service lewat proxy `/api` dengan membaca `/info`.
 */
import { useQuery } from "@tanstack/react-query";

import { errorDetail } from "@/api/client";
import { useAuth } from "@/auth/auth-context";

const INFO_QUERY_KEY = ["info"] as const;

export function HomePage() {
  const { api, session } = useAuth();
  const info = useQuery({
    queryKey: INFO_QUERY_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/info");
      if (data === undefined) {
        throw new Error(errorDetail(error, "Cannot load service info"));
      }
      return data;
    },
  });

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
      <h1 className="text-2xl font-semibold">Hello, {session?.username}</h1>
      <p className="text-muted-foreground">Chat is coming soon.</p>
      <p className="text-sm text-muted-foreground" data-testid="service-status">
        {info.isPending && "Connecting to the agent service…"}
        {info.isError && info.error.message}
        {info.isSuccess &&
          `Connected · ${info.data.agents.length} agents · default ${info.data.default_agent}`}
      </p>
    </div>
  );
}
