import { RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { router } from './router'
import { OfflineBanner } from './components/OfflineBanner'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 1000 * 60,
    },
  },
})

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <OfflineBanner />
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
