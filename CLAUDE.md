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

## Versiones
- Los tags de version siguen semver (vMAYOR.MENOR.PARCHE).
