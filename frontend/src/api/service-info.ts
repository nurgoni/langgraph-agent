/**
 * Info service (`GET /info`): daftar agent, model, dan default-nya. Dipakai pemilih model di
 * composer dan form project, dan di-cache sekali per sesi oleh TanStack Query.
 */
import { useQuery } from "@tanstack/react-query";

import { errorDetail } from "@/api/client";
import { useAuth } from "@/auth/auth-context";

export const SERVICE_INFO_QUERY_KEY = ["info"] as const;
const INFO_FAILED_MESSAGE = "Cannot load service info";

export function useServiceInfo() {
  const { api } = useAuth();
  return useQuery({
    queryKey: SERVICE_INFO_QUERY_KEY,
    queryFn: async () => {
      const { data, error } = await api.GET("/info");
      if (data === undefined) {
        throw new Error(errorDetail(error, INFO_FAILED_MESSAGE));
      }
      return data;
    },
    staleTime: Infinity,
  });
}
