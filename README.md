# Extractor de Anunciantes de Revistas

Software que analiza una revista digital y extrae el listado de sus
anunciantes (marca, web, email, teléfono, sector, páginas), y genera un
informe visual en HTML, además de CSV y JSON.

Pensado para revistas publicadas online con un visor embebido (flipbook),
como las de proarquitectura.es.

---

## Cómo funciona

El proceso tiene cuatro fases:

1. **Obtención** — A partir de la URL, localiza la revista. Si está dentro de
   un visor JavaScript, abre la página con un navegador automatizado
   (Playwright), pasa las páginas y captura el PDF o las imágenes. También
   acepta un PDF que ya tengas descargado.
2. **Páginas** — Convierte la revista en una imagen por página y extrae el
   texto.
3. **Detección** — Identifica los anunciantes. Es **híbrido**:
   - **Modo gratis**: usa el texto y patrones (web, teléfono, email) más
     heurística para distinguir anuncios. Sin coste, sin clave.
   - **Modo IA**: envía cada página al modelo de visión de Claude, que
     reconoce la marca, los datos de contacto y si la página es un anuncio
     real. Más preciso. Requiere una clave de API de Anthropic.
4. **Informe** — Genera `anunciantes_FECHA.html` (informe visual),
   `.csv` (para Excel) y `.json` (para integraciones) en la carpeta `output/`.

Cada ejecucion registra su cobertura con uno de estos estados:

- **completo**: todas las paginas se analizaron correctamente;
- **parcial**: hay paginas o campos que necesitan revision;
- **fallido**: no se pudo analizar ninguna pagina o el documento no contiene
  paginas procesables.

Los informes usan un identificador unico y se escriben primero en archivos
temporales, para que dos exportaciones consecutivas no se sobrescriban ni
dejen entregables a medias.

---

## Instalación

Requiere Python 3.10 o superior.

```bash
pip install -r requirements.txt
playwright install chromium      # necesario para extraer desde una URL
```

El modo IA y el OCR son opcionales; ver comentarios en `requirements.txt`.

---

## Uso

### Interfaz gráfica (recomendado)

```bash
python app.py
```

Pega la URL de la revista (o elige un PDF local), escoge modo Gratis o IA, y
pulsa **Extraer anunciantes**. Al terminar se habilita el botón para abrir el
informe HTML.

### Línea de comandos

```python
from pipeline import run_pipeline

# Desde una URL, modo gratis
run_pipeline(url="https://www.proarquitectura.es/proarquitectura-206-...")

# Desde un PDF local, modo IA
run_pipeline(pdf_path="revista.pdf", use_ai=True, api_key="sk-ant-...")
```

La CLI no exporta automaticamente un analisis parcial. Tras revisar la
cobertura, se puede aceptar de forma explicita con `--permitir-parcial`:

```bash
python cli.py --pdf revista.pdf --ia --permitir-parcial
```

---

## Limitaciones importantes (léelas)

- **Anuncio vs. reportaje**: en revistas del sector, las marcas también
  aparecen en artículos editoriales. El modo gratis no siempre distingue un
  anuncio pagado de una mención editorial; por eso cada resultado lleva un
  porcentaje de **confianza**. Revisa los de confianza media/baja. El modo IA
  es bastante más fiable en esto, pero conviene una revisión final humana.
- **Visores propietarios**: algunos flipbooks (Issuu, FlippingBook) protegen
  el contenido. Si la extracción desde la URL falla, descarga el PDF
  manualmente y usa el modo "PDF local".
- **El modo IA tiene coste** por uso de la API de Anthropic (céntimos por
  revista, según el número de páginas).

---

## Estructura del proyecto

```
revista-anunciantes/
├── app.py              Interfaz gráfica
├── pipeline.py         Orquestador de las cuatro fases
├── requirements.txt
├── core/
│   ├── fetcher.py      Fase 1: localiza y descarga la revista
│   ├── pages.py        Fase 2: PDF/imágenes -> páginas + texto
│   ├── detector.py     Fase 3: detección híbrida (gratis + IA)
│   └── report.py       Fase 4: informe HTML + CSV + JSON
└── output/             Informes generados
```
