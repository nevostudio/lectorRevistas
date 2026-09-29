# Estado del proyecto

## Fase 1 — Integridad del análisis

Completada. Incluye estados completo/parcial/fallido, cobertura visible,
validación de respuestas IA, revisión persistente por trabajo, exportaciones
únicas e idempotentes y pruebas de regresión.

## Fase 2 — Entrada multiformato

Completada el 29 de septiembre de 2026.

- Detección de PDF directo por cabecera, URL o firma real del archivo.
- Conservación de parámetros en enlaces PDF.
- Sesión HTTP compartida y reutilización de cookies obtenidas con Playwright.
- Captura de recursos en la página principal, ventanas nuevas e iframes.
- Reconocimiento explícito del lector autoalojado 3D FlipBook.
- Orden numérico de páginas y conservación de huecos.
- Eliminación de imágenes duplicadas mediante SHA-256.
- Manifiesto de procedencia, tamaño, hash y estado por página.
- Los fallos de descarga pasan a la cobertura y fuerzan estado parcial.
- Pruebas automáticas para PDF directo, enlaces, 3D FlipBook, orden y huecos.

### Límites conocidos para fases posteriores

Los lectores basados exclusivamente en canvas, mosaicos cifrados o sistemas
con autenticación pueden necesitar un adaptador propio. También queda pendiente
reemplazar el máximo genérico de avance del visor por el contador real de cada
plataforma cuando esté disponible.
