# Contexto de producto — Cocina Control

Todo rol lee este archivo ANTES de actuar. Si algo de aca contradice una
decision tecnica, gana este archivo: describe la realidad en la que el
software tiene que funcionar.

## Quien es el usuario

**Los cocineros son los usuarios reales.** Cuatro personas —Dario, Dariana,
Xhyara y Nayeli— arman y despachan los pedidos de Bonabowl, una cocina de
comida saludable en Magdalena del Mar, Lima. Cada una tiene cuenta propia en
el sistema.

**El dueno es un usuario distinto**, no una version con mas permisos del
cocinero. Entra a mirar numeros —consumo, stock, fugas—, no a registrar. Los
campos monetarios NO existen para el cocinero: no son un permiso que falta,
son informacion que no le corresponde al rol.

## En que dispositivo

Tablet montada en la cocina, y celular propio cuando el registro entra por
WhatsApp. **Nunca una computadora de escritorio**: nadie se va a sentar.

La red es la de un local comercial: se cae, se pone lenta, vuelve. La app es
offline-first por necesidad, no por elegancia.

## En que condiciones

Esto es lo que decide casi todos los disenos:

- **Manos ocupadas y con guantes.** Escribir cuesta. Dictar y tocar botones
  grandes no.
- **Hora punta.** Cuando entran los pedidos del almuerzo, cualquier pantalla
  que haga esperar se abandona. No se usa mal: se deja de usar.
- **Ruido.** La campana extractora tapa todo. Una transcripcion de voz puede
  confundir "quince" con "cincuenta" — todo numero dictado se reconfirma.
- **Una sola cosa a la vez.** El operario no compara pantallas ni recuerda un
  dato de la anterior.

## Que valora

**No detenerse.** En ese orden: primero seguir trabajando, despues registrar
completo.

El invariante que sale de ahi y que no se negocia: **el operario jamas espera
al servidor.** La foto se captura, se confirma en pantalla al instante y se
sube en segundo plano. Si la red no esta, el pedido queda pendiente y se
completa despues. Cualquier cambio que rompa esto es un hallazgo bloqueante,
aunque el codigo este impecable.

De ahi tambien: los datos que todavia no existen se dejan vacios, no se
inventan. La cocina no midio gramajes; pedirle un numero en hora punta
produce un dato falso que despues nadie vuelve a cuestionar.

## Restricciones que vienen del negocio

- **Los pedidos llegan de Rappi y PedidosYa**, y las dos plataformas usan
  nombres distintos para lo mismo: "Crispy Salad" / "Bowl crispy", "Filete de
  Pollo" / "Filete grilled". El catalogo se transcribe a mano y se desfasa
  solo cuando cambia la carta.
- **Hay platos fijos y platos armables.** Un `FOCUS BOWL` lleva siempre lo
  mismo; un `ARMA TU BOWL` lo compone el cliente y la unica verdad es el
  ticket de ese pedido.
- **El ticket impreso es la fuente.** El cocinero lo fotografia junto al plato;
  esa foto es el respaldo de lo que salio.
- **Todo es append-only y atribuido.** Nada se borra ni se edita: se corrige
  agregando, y cada fila dice quien la hizo. Si esa atribucion se ensucia, el
  dueno pierde la unica forma que tiene de saber quien conto mal.
- **El asistente de WhatsApp no es un usuario aparte.** Recorre los mismos
  endpoints que la tablet, con token de servicio, y registra **a nombre de la
  persona que le dicto** (cabecera `X-Act-As`). No escribe en la base directo.
  Si existiera un segundo camino de escritura habria dos verdades.

## Para que existe todo esto

Para poder restar: **consumo esperado contra inventario real.** Si se
vendieron 47 bowls, debieron salir 3.7 kg de pollo; si el inventario dice 4.9,
falta 1.2 kg que nadie vendio. Ese es el numero que el dueno necesita.

Cada decision de diseno se juzga contra esa resta. Un dato que no ayuda a
hacerla, y que ademas frena a la cocina, no vale lo que cuesta.
