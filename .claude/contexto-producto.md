# Contexto de producto — Cocina Control

Este archivo es propiedad del repo producto. El sync de fabrica NUNCA lo toca.
Todo rol lo lee ANTES de actuar. Fuente: docs/requerimientos.md (v0.4) y el dueño.

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

## Herramienta E2E (declaración exigida por fabrica)

**Playwright** (`frontend/playwright.config.ts`, `npm run test:e2e`), contra la
app viva — nunca solo seeds. Los tests E2E cubren además el estándar de las
restricciones 1 y 2: ninguna ruta del rol cocinero expone plata ni análisis.
