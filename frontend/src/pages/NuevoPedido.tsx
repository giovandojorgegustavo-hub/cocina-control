/**
 * Pantalla 1 — Cámara al empacar
 * Pantalla 2 — Confirmatorio (PEDIDO GUARDADO)
 *
 * INVARIANTE NO NEGOCIABLE: el operario jamás espera al servidor.
 * El flujo es:
 *  1. Tap disparador → captura frame con canvas
 *  2. Comprime a JPEG ~500 KB
 *  3. Muestra confirmatorio INMEDIATO (Pantalla 2)
 *  4. Encola en IndexedDB para subir en background
 *  5. Tras 1.5 s → navega a /pedidos (bandeja)
 *
 * La subida al servidor ocurre completamente en background, sin bloquear
 * nada. Si falla, reintenta con backoff exponencial.
 */
import { useEffect, useRef, useState, useCallback, type RefObject } from 'react'
import { useNavigate } from 'react-router-dom'
import { enqueuePhoto, flushQueue, compressCanvas } from '../lib/photoQueue'

type ScreenState = 'camera' | 'confirmed' | 'no-camera' | 'permission-denied' | 'photo-too-large'

// Generate a UUID v4 — native if available, fallback otherwise
function generateLocalId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return 'local-' + Math.random().toString(36).slice(2) + Date.now().toString(36)
}

// ---------------------------------------------------------------------------
// Sub-views
// ---------------------------------------------------------------------------

function NoCameraView({ reason }: { reason: 'unavailable' | 'denied' }) {
  const navigate = useNavigate()

  return (
    <div className="h-screen flex flex-col bg-gray-900 text-white">
      <header className="px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate('/')}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver al home"
        >
          &lt;
        </button>
        <h1 className="text-lg font-bold tracking-wide uppercase">PEDIDO — sacale foto al paquete</h1>
      </header>

      <main className="flex-1 flex flex-col items-center justify-center px-8 text-center gap-6">
        {reason === 'unavailable' ? (
          <>
            <p className="text-lg font-semibold">
              Este dispositivo no tiene camara accesible.
            </p>
            <p className="text-gray-400 text-sm">
              Contacta al dueno para resolver el problema.
            </p>
          </>
        ) : (
          <>
            <p className="text-lg font-semibold">
              Sin permiso para usar la camara.
            </p>
            <p className="text-gray-400 text-sm">
              Permiti el acceso a la camara en la configuracion del navegador y volvé a intentar.
            </p>
            <button
              onClick={() => window.location.reload()}
              className="mt-4 bg-white text-gray-900 font-bold text-base px-8 py-4 min-h-[56px] active:opacity-70"
              aria-label="Reintentar acceso a la camara"
            >
              Reintentar
            </button>
          </>
        )}
      </main>
    </div>
  )
}

function ConfirmedView({ time }: { time: string }) {
  return (
    <div
      className="h-screen flex flex-col items-center justify-center bg-gray-900 text-white gap-6"
      role="status"
      aria-live="assertive"
      aria-label="Pedido guardado"
      data-testid="confirmed-view"
    >
      {/* Large green checkmark */}
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 64 64"
        className="w-24 h-24"
        aria-hidden="true"
      >
        <circle cx="32" cy="32" r="30" fill="#16a34a" />
        <path
          d="M18 33 L28 43 L46 22"
          stroke="white"
          strokeWidth="5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>

      <div className="text-center">
        <p className="text-3xl font-black tracking-widest uppercase">PEDIDO GUARDADO</p>
        <p className="mt-3 text-gray-300 text-base">
          {time} — queda PENDIENTE en la bandeja,
        </p>
        <p className="text-gray-300 text-base">completalo cuando puedas</p>
      </div>

      <p className="text-gray-500 text-sm mt-4">volviendo al inicio...</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Photo too large view
// ---------------------------------------------------------------------------

function PhotoTooLargeView({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      className="h-screen flex flex-col items-center justify-center bg-gray-900 text-white gap-6 px-8 text-center"
      data-testid="photo-too-large-view"
    >
      <p className="text-lg font-semibold">La foto es demasiado grande.</p>
      <p className="text-gray-400 text-sm">
        Intentá otra vez con menos zoom.
      </p>
      <button
        onClick={onRetry}
        className="mt-4 bg-white text-gray-900 font-bold text-base px-8 py-4 min-h-[56px] active:opacity-70"
        aria-label="Reintentar foto"
      >
        Reintentar
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main camera view
// ---------------------------------------------------------------------------

function CameraView({
  videoRef,
  onShutter,
}: {
  videoRef: RefObject<HTMLVideoElement>
  onShutter: () => void
}) {
  const navigate = useNavigate()

  return (
    <div className="h-screen flex flex-col bg-gray-900">
      <header className="px-4 py-4 flex items-center gap-3 flex-shrink-0">
        <button
          onClick={() => navigate('/')}
          className="min-h-[48px] min-w-[48px] flex items-center justify-center text-white text-xl font-bold"
          aria-label="Volver al home"
        >
          &lt;
        </button>
        <h1 className="text-lg font-bold tracking-wide uppercase text-white">
          PEDIDO — sacale foto al paquete
        </h1>
      </header>

      {/* Video stream — fills available space */}
      <div className="flex-1 relative overflow-hidden bg-black">
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          className="absolute inset-0 w-full h-full object-cover"
          aria-label="Vista de camara"
        />
        {/* Overlay instruction */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <p className="text-white text-sm font-medium bg-black bg-opacity-40 px-4 py-2 rounded">
            encuadra el paquete
          </p>
        </div>
      </div>

      {/* Shutter area */}
      <div className="flex-shrink-0 bg-gray-900 pb-8 pt-6 flex flex-col items-center gap-4">
        <button
          onClick={onShutter}
          aria-label="Sacar foto"
          data-testid="shutter-button"
          className={[
            'w-20 h-20 rounded-full',
            'bg-white border-4 border-gray-400',
            'flex items-center justify-center',
            'active:scale-95 active:opacity-80',
            'transition-transform duration-75',
            // Ensure minimum touch target
            'min-w-[80px] min-h-[80px]',
          ].join(' ')}
        >
          <span className="sr-only">Sacar foto</span>
          {/* Inner circle — visual affordance */}
          <span className="w-14 h-14 rounded-full bg-white border-2 border-gray-300 block" />
        </button>
        <p className="text-gray-400 text-sm text-center px-4">
          saca la foto y segui — el detalle se completa despues
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export function NuevoPedido() {
  const navigate = useNavigate()
  // useRef<HTMLVideoElement>(null) gives RefObject<HTMLVideoElement> which is
  // assignable to video's `ref` prop without the | null union that TS rejects.
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  // Prevents double-tap from firing the shutter twice (H-02).
  // No reset needed — component unmounts after confirmation.
  const shuttingRef = useRef<boolean>(false)
  const [screen, setScreen] = useState<ScreenState>('camera')
  const [confirmedTime, setConfirmedTime] = useState('')

  // Start the camera stream on mount
  useEffect(() => {
    let cancelled = false

    async function startCamera() {
      if (!navigator.mediaDevices?.getUserMedia) {
        if (!cancelled) setScreen('no-camera')
        return
      }

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment' },
        })
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
        }
      } catch (err) {
        if (cancelled) return
        if (err instanceof DOMException && err.name === 'NotFoundError') {
          setScreen('no-camera')
        } else {
          // NotAllowedError or any other denial
          setScreen('permission-denied')
        }
      }
    }

    void startCamera()

    return () => {
      cancelled = true
      streamRef.current?.getTracks().forEach((t) => t.stop())
    }
  }, [])

  // Ensure the video element gets the stream when it mounts (ref may have been
  // null when the stream arrived)
  useEffect(() => {
    if (videoRef.current && streamRef.current && !videoRef.current.srcObject) {
      videoRef.current.srcObject = streamRef.current
    }
  })

  // Navigate home 1.5 s after confirmation screen appears (H-09: with cleanup)
  useEffect(() => {
    if (screen !== 'confirmed') return
    const t = setTimeout(() => {
      navigate('/', { replace: true })
    }, 1500)
    return () => clearTimeout(t)
  }, [screen, navigate])

  const handleShutter = useCallback(() => {
    // H-02: guard against double-tap
    if (shuttingRef.current) return
    shuttingRef.current = true

    const video = videoRef.current
    if (!video) {
      shuttingRef.current = false
      return
    }

    // 1. Capture frame to canvas
    const canvas = canvasRef.current ?? document.createElement('canvas')
    if (!canvasRef.current) canvasRef.current = canvas

    canvas.width = video.videoWidth || 1280
    canvas.height = video.videoHeight || 720
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      shuttingRef.current = false
      return
    }
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

    // 2. Record display time immediately
    const now = new Date()
    const hh = String(now.getHours()).padStart(2, '0')
    const mm = String(now.getMinutes()).padStart(2, '0')
    const timeStr = `${hh}:${mm}`
    setConfirmedTime(timeStr)

    // 3. Show confirmation screen IMMEDIATELY — before any async work
    setScreen('confirmed')

    // 4. Stop the camera stream (no longer needed)
    streamRef.current?.getTracks().forEach((t) => t.stop())

    // 5. Compress + validate size + enqueue in background (non-blocking) (H-07)
    compressCanvas(canvas, (blob, tooLarge) => {
      if (tooLarge) {
        // Show error state — but confirmation already showed, so we navigate
        // back to camera so they can retry. The confirmation was already shown
        // for UX continuity; we replace with the error state.
        setScreen('photo-too-large')
        return
      }
      if (!blob) return
      const localId = generateLocalId()
      void enqueuePhoto(blob, localId).then(() => {
        // Kick off upload attempt immediately if we're online
        void flushQueue()
      })
    })
  }, [])

  if (screen === 'no-camera') return <NoCameraView reason="unavailable" />
  if (screen === 'permission-denied') return <NoCameraView reason="denied" />
  if (screen === 'confirmed') return <ConfirmedView time={confirmedTime} />
  if (screen === 'photo-too-large') {
    return (
      <PhotoTooLargeView
        onRetry={() => {
          shuttingRef.current = false
          setScreen('camera')
        }}
      />
    )
  }

  return <CameraView videoRef={videoRef} onShutter={handleShutter} />
}
