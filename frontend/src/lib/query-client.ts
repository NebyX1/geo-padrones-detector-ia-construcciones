import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './axios'
export const queryClient = new QueryClient({defaultOptions: {queries: {staleTime: 15000, refetchOnWindowFocus: false,
  retry: (count, error) => count < 1 && (!(error instanceof ApiError) || error.status >= 500)}}})
