interface ErrorBannerProps {
  message: string
  onDismiss?: () => void
  onRetry?: () => void
}

export function ErrorBanner({ message, onDismiss, onRetry }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="fixed bottom-0 left-0 right-0 z-50 bg-red-600 text-white py-3 px-4 flex items-center justify-between"
    >
      <span className="text-sm font-medium">{message}</span>
      <div className="flex items-center gap-2 ml-4">
        {onRetry && (
          <button
            onClick={onRetry}
            className="min-h-[48px] min-w-[48px] px-3 flex items-center justify-center text-white underline text-sm font-semibold"
            aria-label="Reintentar cargar"
          >
            Reintentar
          </button>
        )}
        {onDismiss && (
          <button
            onClick={onDismiss}
            className="min-h-[48px] min-w-[48px] px-3 flex items-center justify-center text-white underline text-sm"
            aria-label="Cerrar error"
          >
            Cerrar
          </button>
        )}
      </div>
    </div>
  )
}
