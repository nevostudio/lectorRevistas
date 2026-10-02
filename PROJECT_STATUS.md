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

### Ampliación de Fase 2 — reanudación de trabajos

Completada el 1 de octubre de 2026.

- Identificador estable por URL o contenido del PDF.
- Descargas y copias de PDF conservadas en `.magazine_work/`.
- Checkpoint atómico por página con imagen, texto incrustado y OCR.
- Checkpoint por pliego IA ligado al modelo, prompt, esquema, imágenes y texto.
- Los pliegos recuperados no vuelven a llamar a Claude.
- Separación entre coste total, coste recuperado y coste nuevo.
- Las capturas incompletas se vuelven a descargar en vez de quedar congeladas.
- Opción visible para reutilizar el trabajo o empezar uno nuevo.
- Opción de CLI `--no-reanudar` para ignorar checkpoints.
- No se guardan claves API ni URLs de recursos con parámetros sensibles.

Un cierre del programa después de un pliego conserva el resultado de ese
pliego. Al repetir la misma revista, el proceso recupera lo terminado y sigue
desde el siguiente punto pendiente.

### Validación real de la Fase 2 con Claude

Completada el 1 de octubre de 2026 con la revista de Clima Noticias de 166
páginas.

- Claude Sonnet 5.5 analizó los 84 pliegos sin fallos de API.
- Coste real estimado por la telemetría: 1,1371 USD.
- Se obtuvieron 67 registros consolidados para revisión.
- La prueba descubrió que 22 pliegos usaban la numeración editorial impresa
  en vez del identificador técnico del PDF. No eran respuestas truncadas: era
  una ambigüedad del contrato de página.
- El esquema enviado a Claude restringe ahora `pagina` a los identificadores
  exactos del pliego y el prompt ordena ignorar la numeración impresa.
- La migración conserva 62 checkpoints válidos y obliga a recalcular solamente
  los 22 afectados. El coste esperado de esa repetición parcial, según el uso
  observado, es aproximadamente 0,284 USD.

El informe de esta primera prueba se conserva como diagnóstico, pero permanece
marcado como parcial. No debe considerarse el informe definitivo de la revista.

### Ampliación de Fase 2 — Excel preparado para base de datos

Completada el 2 de octubre de 2026.

- El `.xlsx` forma parte obligatoria del export final.
- Conserva las hojas `Resumen` y `Anunciantes` para lectura y revisión.
- Añade la hoja `Datos` con nombres de columna técnicos y estables.
- Genera una fila por aparición anunciante/página, con página y confianza como
  valores numéricos.
- Incluye identificadores de anunciante y aparición, estado del análisis,
  fuente, trabajo y exportación para facilitar la carga posterior.
- Teléfonos e identificadores se conservan como texto para evitar pérdidas de
  ceros iniciales.

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
