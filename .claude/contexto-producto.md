# Contexto de producto — Cocina Control

Este archivo es propiedad del repo producto. El sync de fabrica NUNCA lo toca.
Todo rol lo lee ANTES de actuar. Fuente: docs/requerimientos.md (v0.4), el
dueño, y la operacion observada en produccion.

## Quién es el usuario

Dos usuarios con mundos separados a propósito:

- **El cocinero (operario)**: 4 part-time en una dark kitchen de Lima, uno por
  turno, 3-4 días por semana cada uno. Registra lo que pasa: verifica partidas
  que llegan del proveedor, saca la foto del pedido que empaca, cuenta el
  inventario cuando toca. No es personal administrativo ni técnico.
- **El dueño**: pre-carga órdenes de compra con costos, define catálogo y
  recetas, y mira el tablero para cazar fugas de inventario. No está en la
  cocina; decide con los datos que el cocinero capturó.
- Existe un tercer rol **admin** (operario de confianza): ve y carga costos
  como el dueño, pero no ve el tablero.

## En qué dispositivo

- Cocinero: **tablet o celular en la cocina**, pantalla táctil, a veces con
  funda sucia. La app necesita cámara (foto del pedido) y tolerar mala
  conexión: las fotos quedan en cola local si no hay red.
- Dueño: celular o computadora, fuera de la cocina, sin apuro.

## En qué condiciones

- **Cocina prendida**: manos ocupadas, mojadas, sucias o con guantes; apuro
  entre pedidos; ruido; el registro compite con la comida que está en el fuego.
- **El ruido tapa la voz.** Con la campana extractora de fondo, "quince" y
  "cincuenta" suenan igual: todo número dictado se reconfirma antes de
  registrarse, aunque la transcripción venga con confianza alta.
- El proveedor entrega fraccionado y sin horario: la orden de 100 kg llega en
  tandas de 30/40/30 en días distintos, y la recibe quien esté de turno.
- Cada turno lo cubre una persona distinta: nada puede depender de la memoria
  de quien estuvo ayer — todo lo pendiente tiene que estar en la bandeja.

## Qué valora

- **Velocidad sobre todo**: registrar un evento toma **menos de 5 segundos y
  máximo 3 toques**. Confirmar un producto que llegó como se anunció: un toque.
  Botones grandes, respuesta instantánea. Si un flujo pide más, está mal diseñado.
- El dueño valora **confianza en el dato**: conteo a ciegas, verificación sin
  sesgo, y trazabilidad completa (todo evento tiene quién, qué, cuándo).

## Qué restricciones tiene (no negociables)

1. **El cocinero no ve plata NUNCA, en ninguna ruta.** Y las pantallas de
   captura (verificar partida, contar, empacar) no muestran plata para ningún
   rol, ni siquiera el dueño. Costo expuesto en captura = bug crítico con test
   obligatorio.
2. **El cocinero no ve análisis**: ni totales, ni esperados fuera de la lista
   pre-cargada, ni recetas, ni factores, ni discrepancias. El conteo es a ciegas.
3. **Append-only**: nada se borra ni se edita sin rastro; toda corrección es un
   registro nuevo que apunta al original.
4. **Captura en unidad natural** (paltas por unidad, espinaca en gramos, piña
   en latas): nadie convierte nada en el momento de registrar.
5. Moneda única **PEN** (2 decimales). Zona horaria del negocio
   **America/Lima** (configurable por env var). Una sola cocina.
6. **El operario jamás espera al servidor.** La foto se captura, se confirma en
   pantalla al instante y se sube en segundo plano; sin red, el pedido queda
   pendiente y se completa después. Un cambio que rompa esto es hallazgo
   bloqueante aunque el código esté impecable.
7. **Los datos que todavía no existen se dejan vacíos, no se inventan.** La
   cocina no midió gramajes; pedirle un número al operario en hora punta
   produce un dato falso que después nadie vuelve a cuestionar. NULL significa
   "no medido"; cero significaría "medido, y es nada".

## De dónde vienen los pedidos

- **Rappi y PedidosYa**, y las dos plataformas usan nombres distintos para lo
  mismo: "Crispy Salad" / "Bowl crispy", "Filete de Pollo" / "Filete grilled".
  El catálogo se transcribe a mano y se desfasa solo cuando cambia la carta.
- **Hay platos fijos y platos armables.** Un `FOCUS BOWL` lleva siempre lo
  mismo; un `ARMA TU BOWL` lo compone el cliente y la única verdad es el ticket
  de ese pedido.
- **El ticket impreso es la fuente.** El cocinero lo fotografía junto al plato;
  esa foto es el respaldo de lo que salió.

## El asistente de WhatsApp no es un usuario aparte

Recorre los mismos endpoints que la tablet, con token de servicio, y registra
**a nombre de la persona que le dictó** (cabecera `X-Act-As`). No escribe en la
base directo. Si existiera un segundo camino de escritura habría dos verdades y
dos juegos de validaciones que se separan solos.

## Para qué existe todo esto

Para poder restar: **consumo esperado contra inventario real.** Si se vendieron
47 bowls, debieron salir 3.7 kg de pollo; si el inventario dice 4.9, falta
1.2 kg que nadie vendió. Ese es el número que el dueño necesita.

Cada decisión de diseño se juzga contra esa resta. Un dato que no ayuda a
hacerla, y que además frena a la cocina, no vale lo que cuesta.

## Herramienta E2E (declaración exigida por fabrica)

**Playwright** (`frontend/playwright.config.ts`, `npm run test:e2e`), contra la
app viva — nunca solo seeds. Los tests E2E cubren además el estándar de las
restricciones 1 y 2: ninguna ruta del rol cocinero expone plata ni análisis.
