interface ErrorBannerProps {
  message: string
  onDismiss?: () => void
}

export function ErrorBanner({ message, onDismiss }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="fixed bottom-0 left-0 right-0 z-50 bg-red-600 text-white py-3 px-4 flex items-center justify-between"
    >
      <span className="text-sm font-medium">{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="ml-4 min-h-[48px] min-w-[48px] flex items-center justify-center text-white underline text-sm"
          aria-label="Cerrar error"
        >
          Cerrar
        </button>
      )}
    </div>
  )
}
