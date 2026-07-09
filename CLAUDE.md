# Reglas de la Fabrica

## Proceso
- Todo cambio nace en una rama, nunca directo en main.
- Mensajes de commit: formato convencional (tipo: descripcion).
- Antes de commitear: git status y git diff, siempre.

## Estructura
- src/ codigo, tests/ pruebas, migrations/ cambios de BD, docs/ decisiones.

## Pull Requests
- Todo merge a main pasa por Pull Request en GitHub.
- El PR muestra el diff completo: se lee ANTES de aprobar.

## Circuito de revisión (obligatorio por PR)
- Todo PR de código pasa por revisión adversarial de los agentes qa y seguridad ANTES del merge.
- Hallazgos CRÍTICOS o ALTOS son bloqueantes: se corrigen dentro del mismo PR antes de aprobar.
- Hallazgos MEDIOS y BAJOS se registran como issues nuevos en GitHub y se referencian desde el PR.
- El PR queda con un comentario que consolida los hallazgos y su resolución (aplicado en el PR o issue diferido).
- La regla aplica a cada PR sin excepción. No hay "PR chico que no lo necesita".

## Versiones
- Los tags de version siguen semver (vMAYOR.MENOR.PARCHE).
