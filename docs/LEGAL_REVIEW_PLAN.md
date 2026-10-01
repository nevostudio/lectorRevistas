# Fase legal — Plan de revisión

**Estado:** pendiente  
**Ámbito:** España y Unión Europea  
**Momento de cierre:** antes del uso comercial o de entregar bases de contactos

## Objetivo

Determinar en qué condiciones NEVO puede obtener una revista, identificar sus
anunciantes, enriquecer datos de contacto, procesarlos mediante IA y entregar
el resultado a un cliente. La revisión debe distinguir entre:

1. analizar la publicación;
2. crear y conservar el informe;
3. entregar datos al cliente;
4. utilizar esos datos para prospección comercial.

Que una revista o un dato sea visible públicamente no implica por sí solo que
pueda copiarse, reutilizarse o emplearse para cualquier finalidad.

## Bloques de trabajo

### 1. Acceso a revistas y lectores

- Clasificar cada fuente: PDF entregado por el cliente, descarga pública,
  lector web, contenido con cuenta, suscripción o pago.
- Revisar licencia, condiciones de uso y autorización del cliente.
- Comprobar derechos de autor, reproducción temporal y derecho `sui generis`
  sobre bases de datos.
- Prohibir en el producto eludir pagos, controles de acceso o medidas técnicas.
- Definir qué evidencias deben conservarse sobre origen y autorización.

### 2. Datos personales y RGPD/LOPDGDD

- Separar datos puramente societarios de datos de personas físicas.
- Limitar los campos a los necesarios para la localización profesional.
- Determinar quién actúa como responsable y quién como encargado del
  tratamiento en cada modalidad del servicio.
- Documentar finalidad, base jurídica y prueba de interés legítimo cuando sea
  aplicable; no asumir que existe por tratarse de información pública.
- Revisar el deber de información cuando los datos proceden de otra fuente,
  los derechos de acceso, rectificación, supresión y oposición, y el canal para
  ejercerlos.
- Establecer plazos de conservación, borrado, control de acceso, cifrado,
  registro de incidentes y contratos de encargo.
- Evaluar si hace falta una evaluación de impacto y mantener un registro de
  actividades de tratamiento.

### 3. Prospección comercial

- Documentar el uso exacto que NEVO y cada cliente harán del informe.
- Separar llamadas, correo electrónico, SMS, WhatsApp y otros canales: cada
  canal tiene reglas diferentes.
- Verificar consentimiento o excepción aplicable antes de comunicaciones
  electrónicas comerciales.
- Implantar oposición sencilla y gratuita, listas internas de exclusión y, si
  procede, consulta de sistemas de exclusión publicitaria.
- Evitar que el software presente una base extraída como permiso automático
  para contactar.

### 4. Proveedor de IA y transferencias

- Revisar contrato, acuerdo de tratamiento, ubicación, subencargados,
  transferencias internacionales, retención y posible uso para entrenamiento.
- Confirmar qué datos e imágenes se envían a Anthropic y aplicar minimización.
- Impedir que claves API aparezcan en informes, registros o repositorios.
- Documentar el modelo utilizado, finalidad, costes, límites y revisión humana.

### 5. Reglamento europeo de IA

- Determinar el papel de NEVO como proveedor o responsable del despliegue.
- Confirmar la clasificación de riesgo y las obligaciones aplicables en las
  fechas correspondientes.
- Mantener información de uso, limitaciones, supervisión humana y trazabilidad.
- Revisar de nuevo la clasificación si el producto incorpora perfiles de
  personas, decisiones automatizadas o nuevos usos.

### 6. Web, contratos y documentación del producto

- Aviso legal, privacidad y política de cookies de la web.
- Condiciones del servicio, límites de uso y responsabilidades de cada parte.
- Cláusulas del encargo de tratamiento cuando corresponda.
- Garantía del cliente sobre su derecho a proporcionar la revista.
- Política de conservación y borrado de originales, páginas, informes y logs.
- Procedimiento de reclamaciones, rectificaciones y retirada de datos.

## Entregables

- Mapa de datos y proveedores, desde la revista hasta el informe final.
- Matriz `permitido / condicionado / no permitido` por fuente y uso.
- Evaluación de interés legítimo cuando proceda.
- Tabla de conservación y borrado.
- Lista de controles técnicos y cambios de interfaz necesarios.
- Textos legales y cláusulas contractuales para revisión profesional.
- Política de usos prohibidos y procedimiento para ejercer derechos.
- Informe final con riesgos rojos, responsables y fecha de resolución.

## Criterios para cerrar la fase

- Cada método de obtención tiene una autorización o base documentada.
- Los datos personales están minimizados y tienen finalidad, base jurídica,
  conservación y responsable definidos.
- El informe distingue claramente disponer de un contacto de tener permiso
  para enviar una comunicación comercial.
- Existen mecanismos de oposición, exclusión, rectificación y borrado.
- Los contratos con clientes y proveedores reflejan los flujos reales.
- No quedan riesgos rojos sin resolver y la revisión jurídica final está
  documentada.

## Información que habrá que decidir durante la fase

- Quién contratará el servicio y quién decide el uso del informe.
- Si se recogerán nombres, correos nominativos o teléfonos personales.
- Si NEVO enviará comunicaciones o solo entregará el informe.
- Cuánto tiempo se guardarán revistas, imágenes, contactos e informes.
- Si se admitirán fuentes con registro, suscripción o acceso restringido.
- Países en los que se ofrecerá el servicio.

## Fuentes oficiales iniciales

- [Reglamento General de Protección de Datos](https://eur-lex.europa.eu/eli/reg/2016/679/spa)
- [LOPDGDD — Ley Orgánica 3/2018](https://www.boe.es/buscar/act.php?id=BOE-A-2018-16673)
- [AEPD: datos de contacto profesionales](https://www.aepd.es/preguntas-frecuentes/2-tus-obligaciones-como-responsable-del-tratamiento/2-aplicacion-de-la-normativa/FAQ-0203-sobre-la-aplicacion-del-rgpd-a-los-datos-de-contacto)
- [LSSI-CE — Ley 34/2002](https://www.boe.es/buscar/act.php?id=BOE-A-2002-13758)
- [Ley de Propiedad Intelectual](https://www.boe.es/buscar/act.php?id=BOE-A-1996-8930)
- [AEPD: publicidad no deseada](https://www.aepd.es/areas-de-actuacion/publicidad-no-deseada)
- [Reglamento europeo de Inteligencia Artificial](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/spa)

Este documento organiza la revisión y no constituye por sí mismo un dictamen
jurídico ni una conclusión de cumplimiento.
