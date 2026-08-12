import { QueryClient } from "@tanstack/react-query";

export function createQueryClient(retry: boolean | number = 1) {
  return new QueryClient({
    defaultOptions: {
      queries: { retry, staleTime: 15_000, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}
