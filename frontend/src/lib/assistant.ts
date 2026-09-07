import { useMutation } from '@tanstack/react-query'
import { apiClient } from './api'

// ---------------------------------------------------------------------------
// Asistente del panel: POST /assistant/propose
//
// Esta capa SOLO pide la propuesta. No escribe nada: la escritura la hace la
// pantalla, tras un "Confirmar" humano, reusando los hooks de negocio que ya
// existen (pricing, zones, options, promotions) con el token del usuario. El
// asistente no agrega ninguna ruta de escritura nueva.
// ---------------------------------------------------------------------------

export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  role: ChatRole
  content: string
}

// Los tipos de accion de la lista cerrada del backend (api/assistant.py).
export type ProposalType =
  | 'set_price'
  | 'set_zone'
  | 'new_zone'
  | 'set_promotion'
  | 'set_option_item'
  | 'new_option_item'
  | 'set_option_group'
  | 'assign_groups'

// La propuesta ya validada contra la base. Los campos presentes dependen del
// type; el backend solo incluye los que se van a cambiar.
export interface AssistantProposal {
  type: ProposalType
  // Nombres legibles que el backend agrega para el resumen de la tarjeta.
  product_name?: string
  district?: string
  group_name?: string
  name?: string
  // Identificadores para el hook de negocio.
  product_id?: string
  zone_id?: string
  option_item_id?: string
  group_id?: string
  group_ids?: string[]
  code?: string
  // Parametros del cambio (importes/porcentajes como string con dos decimales).
  sale_price?: string
  discount_percent?: string
  fee?: string
  price?: string
  percent?: string
  is_active?: boolean
  first_order_only?: boolean
}

export interface AssistantProposeResponse {
  reply: string
  proposal: AssistantProposal | null
  summary: string | null
}

async function propose(messages: ChatMessage[]): Promise<AssistantProposeResponse> {
  const response = await apiClient.post<AssistantProposeResponse>('/assistant/propose', {
    messages,
  })
  return response.data
}

export function useProposeAssistant() {
  return useMutation({
    mutationFn: (messages: ChatMessage[]) => propose(messages),
  })
}
