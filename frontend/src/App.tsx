import { RouterProvider } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { router } from './router'
import { OfflineBanner } from './components/OfflineBanner'
import { queryClient } from './lib/queryClient'

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <OfflineBanner />
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}
