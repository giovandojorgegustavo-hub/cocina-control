import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { isAxiosError } from 'axios'
import { ErrorBanner } from '../components/ErrorBanner'
import { useProposeAssistant } from '../lib/assistant'
import type { AssistantProposal, ChatMessage } from '../lib/assistant'
import { useUpdateProductPricing, useUpdatePromotion } from '../lib/pricing'
import { useCreateZone, useUpdateZone } from '../lib/zones'
import {
  useCreateOptionItem,
  useReplaceProductOptionGroups,
  useUpdateOptionGroup,
  useUpdateOptionItem,
} from '../lib/options'

// ---------------------------------------------------------------------------
// Asistente del panel (issue: chat interno).
//
// La pantalla habla en espanol y solo PROPONE: el backend nunca escribe. Cuando
// hay una propuesta, se muestra una tarjeta con el resumen y un boton Confirmar.
// Recien ahi la pantalla llama al endpoint de negocio que ya existe, con el
// token del usuario, reusando los mismos hooks que las pantallas de la carta.
// El asistente no agrega ningun poder nuevo: es lenguaje natural sobre acciones
// que el dueno ya puede hacer con clics, con el mismo rol y un confirm humano.
// ---------------------------------------------------------------------------

const EXAMPLES = [
  'sube el Focus Bowl a 35',
  'desactiva Breña',
  'pon 10% de descuento al Energy Bowl',
]

function errorMessage(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  return fallback
}

interface Bubble extends ChatMessage {
  id: number
}

export function Asistente() {
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Bubble[]>([])
  const [input, setInput] = useState('')
  const [proposal, setProposal] = useState<AssistantProposal | null>(null)
  const [summary, setSummary] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [applying, setApplying] = useState(false)
  const nextId = useRef(1)

  const propose = useProposeAssistant()

  // Hooks de negocio: la escritura reusa exactamente estos, con el token del
  // usuario. Se instancian arriba (reglas de hooks) y se despachan por type.
  const updatePricing = useUpdateProductPricing()
  const updateZone = useUpdateZone()
  const createZone = useCreateZone()
  const updatePromotion = useUpdatePromotion()
  const updateOptionItem = useUpdateOptionItem()
  const createOptionItem = useCreateOptionItem()
  const updateOptionGroup = useUpdateOptionGroup()
  const replaceGroups = useReplaceProductOptionGroups()

  function addBubble(role: 'user' | 'assistant', content: string) {
    setMessages((prev) => [...prev, { id: nextId.current++, role, content }])
  }

  function send(text: string) {
    const trimmed = text.trim()
    if (!trimmed || propose.isPending) return
    setError(null)
    setProposal(null)
    setSummary(null)

    const outgoing: ChatMessage[] = [
      ...messages.map(({ role, content }) => ({ role, content })),
      { role: 'user', content: trimmed },
    ]
    addBubble('user', trimmed)
    setInput('')

    propose.mutate(outgoing, {
      onSuccess: (data) => {
        addBubble('assistant', data.reply)
        if (data.proposal) {
          setProposal(data.proposal)
          setSummary(data.summary)
        }
      },
      onError: (err) => {
        if (isAxiosError(err) && err.response?.status === 503) {
          setError('El asistente no está configurado — pídele al equipo la clave.')
          return
        }
        setError(errorMessage(err, 'No se pudo consultar al asistente.'))
      },
    })
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    send(input)
  }

  // Traduce la propuesta al hook de negocio correspondiente y devuelve una
  // linea de resultado. No hay ninguna ruta nueva: cada rama es un endpoint
  // que el usuario ya podia usar desde la carta.
  async function applyProposal(p: AssistantProposal): Promise<string> {
    switch (p.type) {
      case 'set_price': {
        const input: { sale_price?: string; discount_percent?: string } = {}
        if (p.sale_price !== undefined) input.sale_price = p.sale_price
        if (p.discount_percent !== undefined) input.discount_percent = p.discount_percent
        const data = await updatePricing.mutateAsync({ productId: p.product_id!, input })
        return `${data.name}: precio S/ ${data.sale_price ?? '—'}${
          data.discount_percent && data.discount_percent !== '0.00'
            ? `, ${data.discount_percent}% de descuento`
            : ''
        }`
      }
      case 'set_zone': {
        const input: { fee?: string; is_active?: boolean } = {}
        if (p.fee !== undefined) input.fee = p.fee
        if (p.is_active !== undefined) input.is_active = p.is_active
        const data = await updateZone.mutateAsync({ id: p.zone_id!, input })
        return `${data.district}: S/ ${data.fee}, ${data.is_active ? 'activa' : 'apagada'}`
      }
      case 'new_zone': {
        const data = await createZone.mutateAsync({ district: p.district!, fee: p.fee! })
        return `${data.district} agregada a S/ ${data.fee}`
      }
      case 'set_promotion': {
        const input: { percent?: string; is_active?: boolean; first_order_only?: boolean } = {}
        if (p.percent !== undefined) input.percent = p.percent
        if (p.is_active !== undefined) input.is_active = p.is_active
        if (p.first_order_only !== undefined) input.first_order_only = p.first_order_only
        const data = await updatePromotion.mutateAsync({ code: p.code!, input })
        return `${data.name}: ${data.percent}%, ${data.is_active ? 'activa' : 'apagada'}`
      }
      case 'set_option_item': {
        const input: { name?: string; price?: string; is_active?: boolean } = {}
        if (p.name !== undefined) input.name = p.name
        if (p.price !== undefined) input.price = p.price
        if (p.is_active !== undefined) input.is_active = p.is_active
        const data = await updateOptionItem.mutateAsync({ id: p.option_item_id!, input })
        return `${data.name}: S/ ${data.price}, ${data.is_active ? 'activa' : 'apagada'}`
      }
      case 'new_option_item': {
        const data = await createOptionItem.mutateAsync({
          groupId: p.group_id!,
          input: { name: p.name!, price: p.price! },
        })
        return `${data.name} agregada a S/ ${data.price}`
      }
      case 'set_option_group': {
        const input: { name?: string; is_active?: boolean } = {}
        if (p.name !== undefined) input.name = p.name
        if (p.is_active !== undefined) input.is_active = p.is_active
        const data = await updateOptionGroup.mutateAsync({ id: p.group_id!, input })
        return `${data.name}: ${data.is_active ? 'activo' : 'apagado'}`
      }
      case 'assign_groups': {
        const data = await replaceGroups.mutateAsync({
          productId: p.product_id!,
          groupIds: p.group_ids ?? [],
        })
        return `${p.product_name ?? 'plato'}: ${data.length} grupo(s) asignado(s)`
      }
      default:
        throw new Error('Acción no soportada')
    }
  }

  async function handleConfirm() {
    if (!proposal || applying) return
    setError(null)
    setApplying(true)
    try {
      const resultado = await applyProposal(proposal)
      addBubble('assistant', `Listo: ${resultado}`)
      setProposal(null)
      setSummary(null)
    } catch (err) {
      setError(errorMessage(err, 'No se pudo aplicar el cambio.'))
    } finally {
      setApplying(false)
    }
  }

  function handleDiscard() {
    setProposal(null)
    setSummary(null)
    addBubble('assistant', 'Descartado. ¿Querés pedir otra cosa?')
  }

  const empty = messages.length === 0

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <header className="bg-gray-900 text-white px-4 py-4 flex items-center gap-4 flex-shrink-0">
        <button
          onClick={() => navigate('/')}
          className="min-h-[48px] min-w-[48px] px-2 text-sm text-gray-300 underline"
          aria-label="Volver al inicio"
        >
          ← inicio
        </button>
        <h1 className="text-xl font-bold tracking-wide">Asistente</h1>
      </header>

      <main className="flex-1 px-4 py-6 overflow-y-auto">
        {empty ? (
          <div className="max-w-md mx-auto text-center text-gray-600">
            <p className="text-base">
              Escribime en español qué querés cambiar de la carta, las zonas, las promociones
              o las opciones. Te muestro la propuesta y vos confirmás.
            </p>
            <p className="mt-6 text-xs font-bold uppercase tracking-widest text-gray-500">
              Ejemplos
            </p>
            <ul className="mt-3 flex flex-col gap-2">
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button
                    onClick={() => send(example)}
                    className="w-full px-4 py-3 bg-white border border-gray-300 rounded-lg text-left text-sm text-gray-800 active:bg-gray-100"
                  >
                    “{example}”
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <ul
            className="max-w-md mx-auto flex flex-col gap-3"
            aria-live="polite"
            aria-label="Conversación con el asistente"
          >
            {messages.map((m) => (
              <li
                key={m.id}
                className={m.role === 'user' ? 'self-end max-w-[85%]' : 'self-start max-w-[85%]'}
                data-role={m.role}
              >
                <div
                  className={[
                    'px-4 py-2 rounded-2xl text-sm whitespace-pre-wrap',
                    m.role === 'user'
                      ? 'bg-gray-900 text-white rounded-br-sm'
                      : 'bg-white border border-gray-200 text-gray-800 rounded-bl-sm',
                  ].join(' ')}
                >
                  {m.content}
                </div>
              </li>
            ))}
            {propose.isPending && (
              <li className="self-start text-sm text-gray-500" aria-label="El asistente está escribiendo">
                Pensando…
              </li>
            )}
          </ul>
        )}

        {proposal && (
          <section
            className="max-w-md mx-auto mt-4 bg-white border-2 border-gray-900 rounded-lg p-4"
            aria-label="Propuesta del asistente"
          >
            <p className="text-xs font-bold uppercase tracking-widest text-gray-500">Propuesta</p>
            <p className="mt-2 text-base text-gray-900">{summary ?? 'Aplicar este cambio.'}</p>
            <div className="mt-4 flex gap-3">
              <button
                onClick={handleConfirm}
                disabled={applying}
                className={[
                  'flex-1 min-h-[48px] px-4 text-sm font-bold uppercase tracking-wide rounded',
                  applying
                    ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-gray-900 text-white active:opacity-70',
                ].join(' ')}
              >
                {applying ? 'Aplicando…' : 'Confirmar'}
              </button>
              <button
                onClick={handleDiscard}
                disabled={applying}
                className="flex-1 min-h-[48px] px-4 text-sm font-bold uppercase tracking-wide rounded border border-gray-300 text-gray-700 active:bg-gray-100"
              >
                Descartar
              </button>
            </div>
          </section>
        )}
      </main>

      <footer className="bg-white border-t border-gray-200 px-4 py-3 flex-shrink-0">
        <form onSubmit={handleSubmit} className="max-w-md mx-auto flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Escribí un mensaje…"
            aria-label="Mensaje para el asistente"
            className="flex-1 px-3 py-2 border border-gray-300 bg-white text-base rounded focus:outline-none focus:ring-2 focus:ring-gray-900 min-h-[48px]"
          />
          <button
            type="submit"
            disabled={input.trim() === '' || propose.isPending}
            className={[
              'min-h-[48px] px-5 text-sm font-bold uppercase tracking-wide rounded',
              input.trim() === '' || propose.isPending
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : 'bg-gray-900 text-white active:opacity-70',
            ].join(' ')}
          >
            Enviar
          </button>
        </form>
      </footer>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
    </div>
  )
}
