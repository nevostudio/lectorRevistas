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

### Actualización del análisis IA — preparada, pendiente de prueba real

- Modelo por defecto actualizado de Claude Sonnet 4.6 a Claude Sonnet 5.5.
- Structured Outputs activo mediante un esquema JSON estricto para anuncios.
- Tarifas de entrada, salida y caché actualizadas para calcular el coste.
- El modelo exacto utilizado queda guardado en los metadatos del informe.
- Validación local mantenida como segunda barrera ante datos incoherentes.
- Verificación automatizada con respuestas simuladas, sin consumir API.

La comparación con el informe real anterior queda aplazada por decisión del
usuario. No se ha enviado ninguna página ni realizado ninguna llamada de pago.

### Ampliación de Fase 2 — comprobación previa de la fuente

Completada el 30 de septiembre de 2026.

- Diagnóstico automático antes de detectar anunciantes.
- Identificación visible de PDF local, PDF remoto o lector por imágenes.
- Comparación entre páginas esperadas y obtenidas cuando el visor publica el
  total; detección de huecos internos cuando solo existe numeración parcial.
- Validación de archivos ausentes, vacíos, dañados y con baja resolución.
- Detección de números de página duplicados y descargas fallidas.
- Registro explícito de imágenes duplicadas dentro del manifiesto de origen.
- Lectura conservadora de contadores de página habituales en lectores web.
- El recorrido del visor usa el total detectado en lugar del límite genérico
  de 80 avances, con un máximo de seguridad de 1.000.
- Bloqueo del modo IA cuando la fuente está incompleta, antes de realizar una
  llamada a Claude. El modo gratis puede continuar, marcado como parcial.
- Diagnóstico guardado en `comprobacion_fuente` dentro de los metadatos.
- Paso visible «Comprobando integridad» añadido al progreso de la aplicación.

Cuando el lector no publica un total fiable, el programa lo indica y valida
las páginas observadas sin afirmar que la edición esté completa.

## Fase legal — Cumplimiento en España y la Unión Europea

**Estado:** pendiente. Debe completarse antes de explotar comercialmente el
software o entregar bases de contactos a clientes.

El plan detallado está en [`docs/LEGAL_REVIEW_PLAN.md`](docs/LEGAL_REVIEW_PLAN.md).
La revisión cubrirá obtención de revistas, propiedad intelectual y derechos
sobre bases de datos, protección de datos, prospección comercial, proveedores
de IA, seguridad, conservación, contratos y Reglamento europeo de IA.

La fase producirá una matriz de riesgos y cambios concretos para el producto.
La conclusión final deberá validarse con un profesional jurídico especializado
en protección de datos, propiedad intelectual y comercio electrónico.
