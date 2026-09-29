"""
app.py
------
Interfaz grafica del Extractor de Anunciantes de Revistas.

Pegas una URL (o eliges un PDF local), eliges modo gratis o modo IA, y al
terminar se abre el informe HTML "bonito". Toda la logica pesada corre en un
hilo aparte para que la ventana no se congele.

Lanzar con:  python app.py
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import run_extraction, export_results  # noqa: E402
from core.detector import review_flag_label  # noqa: E402
from core import config  # noqa: E402

try:
    from PIL import Image, ImageTk
    PIL_TK = True
except ImportError:
    PIL_TK = False

# Paleta Nevo Studio (ver /Nevo/Web/Nevo web/nevo-studio/app/globals.css).
BG      = "#ffffff"   # papel
INK     = "#0a0a0a"   # tinta
ACCENT  = "#ff4b00"   # naranja Nevo
GREEN   = "#0a0a0a"   # CTA secundario: negro Nevo
CARD    = "#f4f4f2"   # gris-50
LINE    = "#ececea"   # gris-100
MUTE    = "#9a9a97"   # gris-400
DARK2   = "#2a2a28"   # gris-800

# Tipografias: aproximamos el "display" (Big Shoulders) con Arial Narrow bold,
# el sans (Instrument) con Helvetica y el mono (Geist) con Menlo/SF Mono.
F_DISPLAY = ("Arial Narrow", 22, "bold")
F_SANS    = ("Helvetica", 10)
F_SANS_B  = ("Helvetica", 10, "bold")
F_MONO    = ("Menlo", 9)
F_MONO_S  = ("Menlo", 8)
F_MONO_B  = ("Menlo", 9, "bold")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NEVO · Extractor de Anunciantes")
        self.geometry("820x720")
        self.configure(bg=BG)
        self.minsize(720, 620)

        self.pdf_path: str | None = None
        self.last_result: dict | None = None
        self.extract_result: dict | None = None

        self._build_ui()

    # ------------------------------------------------------------------ #
    def _build_ui(self):
        # --- Cabecera Nevo -----------------------------------------------
        head = tk.Frame(self, bg=INK, height=104)
        head.pack(fill="x")
        head.pack_propagate(False)

        brand_row = tk.Frame(head, bg=INK)
        brand_row.pack(anchor="w", padx=28, pady=(22, 0))

        # Monograma N (cuadrado negro con borde naranja sutil).
        mono = tk.Canvas(brand_row, width=34, height=34, bg=INK,
                         highlightthickness=0)
        mono.create_rectangle(0, 0, 34, 34, fill=ACCENT, outline="")
        mono.create_text(17, 18, text="N", fill="white",
                         font=("Arial Narrow", 22, "bold"))
        mono.pack(side="left")

        # Wordmark NEVO con barrita naranja bajo la E.
        wm = tk.Canvas(brand_row, width=130, height=34, bg=INK,
                       highlightthickness=0)
        wm.create_text(8, 17, anchor="w", text="NEVO", fill="white",
                       font=("Arial Narrow", 26, "bold"))
        wm.create_rectangle(34, 28, 56, 31, fill=ACCENT, outline="")
        wm.pack(side="left", padx=(10, 0))

        tk.Label(head, text="EXTRACTOR DE ANUNCIANTES", bg=INK, fg="white",
                 font=("Arial Narrow", 14, "bold")).pack(anchor="w",
                                                          padx=28,
                                                          pady=(6, 0))
        tk.Label(head,
                 text="INTELIGENCIA COMPETITIVA  ·  REVISTAS DEL SECTOR",
                 bg=INK, fg=MUTE, font=F_MONO_S).pack(anchor="w", padx=28)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=28, pady=22)

        # --- Entrada: URL -------------------------------------------------
        tk.Label(body, text="URL DE LA REVISTA", bg=BG, fg=MUTE,
                 font=F_MONO_B).pack(anchor="w")
        self.url_var = tk.StringVar()
        url_entry = tk.Entry(body, textvariable=self.url_var,
                             font=F_SANS, bg="white", fg=INK,
                             relief="flat", highlightthickness=1,
                             highlightbackground=LINE,
                             highlightcolor=ACCENT,
                             insertbackground=INK)
        url_entry.pack(fill="x", ipady=8, pady=(6, 4))
        url_entry.insert(0, config.last_url() or
                         "https://www.proarquitectura.es/proarquitectura-"
                         "206-especial-arquitectura-industrializada/")

        # --- Entrada: PDF local (alternativa) -----------------------------
        pdf_row = tk.Frame(body, bg=BG)
        pdf_row.pack(fill="x", pady=(4, 14))
        self.pdf_label = tk.Label(pdf_row, text="O ELIGE UN PDF LOCAL  ·  "
                                  "NINGUN ARCHIVO SELECCIONADO", bg=BG,
                                  fg=MUTE, font=F_MONO_S)
        self.pdf_label.pack(side="left")
        tk.Button(pdf_row, text="Elegir PDF", command=self._choose_pdf,
                  bg=CARD, fg=INK, relief="flat", font=F_SANS,
                  activebackground=LINE, activeforeground=INK,
                  cursor="hand2", padx=14, pady=4,
                  borderwidth=0).pack(side="right")

        # --- Opciones -----------------------------------------------------
        opt = tk.LabelFrame(body, text=" MODO DE DETECCION ", bg=BG, fg=INK,
                            font=F_MONO_B, relief="solid",
                            bd=1, highlightbackground=LINE,
                            labelanchor="nw")
        opt.pack(fill="x", pady=10)

        self.mode = tk.StringVar(value="gratis")
        tk.Radiobutton(opt, text="Gratis  ·  texto y patrones, sin coste, "
                       "menos preciso", variable=self.mode, value="gratis",
                       bg=BG, fg=INK, font=F_SANS,
                       selectcolor="white", activebackground=BG,
                       anchor="w",
                       command=self._toggle_key).pack(fill="x", padx=12,
                                                      pady=(8, 0))
        tk.Radiobutton(opt, text="IA  ·  analisis visual con Claude, mas "
                       "preciso, requiere clave", variable=self.mode,
                       value="ia", bg=BG, fg=INK, font=F_SANS,
                       selectcolor="white", activebackground=BG,
                       anchor="w",
                       command=self._toggle_key).pack(fill="x", padx=12,
                                                      pady=(0, 6))

        key_row = tk.Frame(opt, bg=BG)
        key_row.pack(fill="x", padx=12, pady=(0, 4))
        tk.Label(key_row, text="ANTHROPIC_API_KEY", bg=BG, fg=MUTE,
                 font=F_MONO_S).pack(side="left")
        self.key_var = tk.StringVar(value=config.api_key())
        self.key_entry = tk.Entry(key_row, textvariable=self.key_var,
                                  show="*", font=F_MONO,
                                  bg="white", fg=INK, relief="flat",
                                  highlightthickness=1,
                                  highlightbackground=LINE,
                                  highlightcolor=ACCENT,
                                  state="disabled")
        self.key_entry.pack(side="left", fill="x", expand=True, padx=10,
                            ipady=4)

        # Recordar la clave entre sesiones (guardada localmente, solo lectura
        # del propietario). Marcada por defecto si ya habia una guardada.
        self.remember_key = tk.BooleanVar(value=bool(config.get("api_key")))
        self.remember_chk = tk.Checkbutton(
            opt, text="Recordar la clave en este equipo",
            variable=self.remember_key, bg=BG, fg=MUTE, font=F_MONO_S,
            selectcolor="white", activebackground=BG, anchor="w",
            state="disabled", command=self._toggle_remember)
        self.remember_chk.pack(fill="x", padx=12, pady=(0, 10))

        # --- Boton de accion ---------------------------------------------
        self.run_btn = tk.Button(body, text="EXTRAER ANUNCIANTES",
                                 command=self._on_run,
                                 bg=ACCENT, fg="white",
                                 activebackground=DARK2,
                                 activeforeground="white",
                                 relief="flat",
                                 font=("Arial Narrow", 13, "bold"),
                                 cursor="hand2", pady=13, borderwidth=0)
        self.run_btn.pack(fill="x", pady=(14, 10))

        # --- Consola de progreso -----------------------------------------
        tk.Label(body, text="PROGRESO", bg=BG, fg=MUTE,
                 font=F_MONO_B).pack(anchor="w")
        console_frame = tk.Frame(body, bg=INK, highlightthickness=0)
        console_frame.pack(fill="both", expand=True, pady=(6, 8))
        self.console = tk.Text(console_frame, bg=INK, fg="#d4d4d2",
                               font=F_MONO, relief="flat",
                               wrap="word", state="disabled", padx=14,
                               pady=12, insertbackground="white",
                               borderwidth=0)
        self.console.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(console_frame, command=self.console.yview)
        sb.pack(side="right", fill="y")
        self.console.config(yscrollcommand=sb.set)

        # --- Pie con resultado -------------------------------------------
        self.result_btn = tk.Button(body, text="ABRIR INFORME HTML",
                                    command=self._open_report,
                                    bg=INK, fg="white",
                                    activebackground=DARK2,
                                    activeforeground="white",
                                    relief="flat",
                                    font=("Arial Narrow", 12, "bold"),
                                    cursor="hand2", pady=10,
                                    state="disabled", borderwidth=0)
        self.result_btn.pack(fill="x")

        # --- Acceso a la biblioteca de revistas --------------------------
        self.library_btn = tk.Button(body, text="BIBLIOTECA · COMPARAR NUMEROS",
                                     command=self._open_library,
                                     bg=BG, fg=INK,
                                     activebackground=CARD,
                                     activeforeground=INK,
                                     relief="flat",
                                     font=F_MONO_B,
                                     cursor="hand2", pady=9,
                                     borderwidth=1,
                                     highlightbackground=LINE,
                                     highlightthickness=1)
        self.library_btn.pack(fill="x", pady=(8, 0))

    def _open_library(self):
        LibraryWindow(self)

    # ------------------------------------------------------------------ #
    def _toggle_key(self):
        ia = self.mode.get() == "ia"
        self.key_entry.config(state="normal" if ia else "disabled")
        self.remember_chk.config(state="normal" if ia else "disabled")

    def _toggle_remember(self):
        # Si el usuario desmarca, olvidamos la clave guardada de inmediato.
        if not self.remember_key.get():
            config.forget_api_key()

    def _choose_pdf(self):
        path = filedialog.askopenfilename(
            title="Elige el PDF de la revista",
            filetypes=[("PDF", "*.pdf")])
        if path:
            self.pdf_path = path
            self.pdf_label.config(
                text=f"PDF · {os.path.basename(path).upper()}", fg=INK)

    def _log(self, msg: str):
        self.console.config(state="normal")
        self.console.insert("end", msg + "\n")
        self.console.see("end")
        self.console.config(state="disabled")
        self.update_idletasks()

    # ------------------------------------------------------------------ #
    def _on_run(self):
        url = self.url_var.get().strip()
        if not url and not self.pdf_path:
            messagebox.showwarning("Faltan datos",
                                   "Indica una URL o elige un PDF local.")
            return
        if self.mode.get() == "ia" and not self.key_var.get().strip():
            messagebox.showwarning(
                "Falta la clave",
                "El modo IA necesita una clave de API de Anthropic.\n"
                "Cambia a modo gratis o introduce la clave.")
            return

        # Persistimos URL y (si procede) la clave para la proxima sesion.
        if url:
            config.set_last_url(url)
        if self.mode.get() == "ia" and self.remember_key.get():
            key = self.key_var.get().strip()
            if key:
                config.remember_api_key(key)

        self.run_btn.config(state="disabled", text="PROCESANDO...")
        self.result_btn.config(state="disabled",
                               text="ABRIR INFORME HTML",
                               command=self._open_report,
                               bg=INK, fg="white")
        self.console.config(state="normal")
        self.console.delete("1.0", "end")
        self.console.config(state="disabled")

        threading.Thread(target=self._worker, daemon=True,
                         args=(url,)).start()

    def _worker(self, url: str):
        try:
            result = run_extraction(
                url=url or None,
                pdf_path=self.pdf_path,
                use_ai=(self.mode.get() == "ia"),
                api_key=self.key_var.get().strip() or None,
                run_ocr=True,
                progress=lambda m: self.after(0, self._log, m),
            )
            if not result.get("ok"):
                self.after(0, self._log,
                           f"\n>>> ERROR: {result.get('error')}")
                return
            self.extract_result = result
            self.after(0, self._after_extraction)
        except Exception as e:  # noqa: BLE001
            self.after(0, self._log, f"\n>>> EXCEPCION: {e}")
        finally:
            self.after(0, lambda: self.run_btn.config(
                state="normal", text="EXTRAER ANUNCIANTES"))

    # ------------------------------------------------------------------ #
    # Post-extraccion: decidir entre revision manual o export directo
    # ------------------------------------------------------------------ #
    def _after_extraction(self):
        r = self.extract_result
        advertisers = r["advertisers"]
        flagged = [a for a in advertisers if a.review_flag]
        n_total = len(advertisers)
        n_flag = len(flagged)
        status = r.get("analysis_status", "completo")
        if status == "parcial" and not advertisers:
            self._log("\n>>> ANALISIS PARCIAL SIN RESULTADOS. Revisa las "
                      "paginas pendientes antes de generar un informe.")
            self.result_btn.config(state="disabled")
            return
        if n_flag:
            prefix = "Analisis parcial; " if status == "parcial" else ""
            self._log(f"\n>>> {prefix}{n_total} anunciantes detectados; "
                      f"{n_flag} necesitan revision.")
            self.result_btn.config(
                text=f"REVISAR  {n_flag}  CASOS DUDOSOS",
                command=self._open_review,
                bg=ACCENT, fg="white",
                activebackground=DARK2,
                state="normal")
        else:
            self._log(f"\n>>> {n_total} anunciantes; ninguno requiere "
                      f"revision manual.")
            self._finalize_export()

    def _open_review(self):
        r = self.extract_result
        ReviewWindow(self, r["advertisers"], r["pages"],
                     on_done=self._on_review_done)

    def _on_review_done(self, kept_advertisers: list):
        self.extract_result["advertisers"] = kept_advertisers
        n_total = len(kept_advertisers)
        self._log(f"\n>>> Revision terminada. {n_total} anunciantes "
                  f"confirmados.")
        self._finalize_export()

    def _finalize_export(self):
        r = self.extract_result
        outdir = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), "output")
        try:
            paths = export_results(
                r["advertisers"], r["meta"], outdir, progress=self._log)
        except Exception as e:  # noqa: BLE001
            self._log(f"\n>>> ERROR al exportar: {e}")
            return
        r["paths"] = paths
        self.last_result = r
        n = len(r["advertisers"])
        self._log(f"\n>>> {n} anunciantes en el informe final.")
        self.result_btn.config(
            text="ABRIR INFORME HTML",
            command=self._open_report,
            bg=INK, fg="white",
            activebackground=DARK2,
            state="normal")

    def _open_report(self):
        if self.last_result and self.last_result.get("paths"):
            html_path = self.last_result["paths"]["html"]
            webbrowser.open(f"file://{os.path.abspath(html_path)}")


# --------------------------------------------------------------------------- #
# Ventana de revision manual de casos dudosos
# --------------------------------------------------------------------------- #
class ReviewWindow(tk.Toplevel):
    """Muestra los anunciantes marcados como dudosos para confirmar o descartar.

    A la izquierda, lista de los flagged con su estado (pendiente/confirmado/
    descartado). A la derecha, el detalle del actual con previa de la pagina,
    campos editables (marca, sector, web...) y botones de decision.

    Al pulsar "TERMINAR Y EXPORTAR" se devuelve la lista final via on_done:
      - los no marcados pasan tal cual
      - los flagged confirmados pasan (con las ediciones aplicadas)
      - los flagged descartados se eliminan
      - los flagged que queden "pendientes" se mantienen por defecto (la
        marca aun esta, pero el usuario podra filtrar despues por confianza).
    """

    STATE_PENDING = "pending"
    STATE_KEEP = "keep"
    STATE_DROP = "drop"

    STATE_LABEL = {
        STATE_PENDING: "PENDIENTE",
        STATE_KEEP: "CONFIRMADO",
        STATE_DROP: "DESCARTADO",
    }
    STATE_COLOR = {
        STATE_PENDING: MUTE,
        STATE_KEEP: INK,
        STATE_DROP: ACCENT,
    }

    def __init__(self, parent, advertisers: list, pages: list, on_done):
        super().__init__(parent)
        self.title("NEVO · Revision de casos dudosos")
        self.configure(bg=BG)
        self.geometry("1180x760")
        self.minsize(960, 640)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.on_done = on_done
        self.all_advertisers = advertisers
        self.flagged = [a for a in advertisers if a.review_flag]
        self.non_flagged = [a for a in advertisers if not a.review_flag]
        self.pages_by_num = {p.number: p for p in pages}

        # Estado por anunciante flagged (mismo orden).
        self.states = [self.STATE_PENDING] * len(self.flagged)
        # Cache de PhotoImage para no perderlas por GC.
        self._img_cache: dict[int, "ImageTk.PhotoImage"] = {}
        self.idx = 0

        self._build_ui()
        self._refresh_list()
        if self.flagged:
            self._show(0)
        # Modal sobre la app principal.
        self.grab_set()
        self.focus_set()

    # ------------------------------------------------------------------ #
    def _build_ui(self):
        # --- Cabecera Nevo -----------------------------------------------
        head = tk.Frame(self, bg=INK, height=88)
        head.pack(fill="x")
        head.pack_propagate(False)

        brand = tk.Frame(head, bg=INK)
        brand.pack(side="left", padx=24, pady=18)

        mono = tk.Canvas(brand, width=30, height=30, bg=INK,
                          highlightthickness=0)
        mono.create_rectangle(0, 0, 30, 30, fill=ACCENT, outline="")
        mono.create_text(15, 16, text="N", fill="white",
                          font=("Arial Narrow", 19, "bold"))
        mono.pack(side="left")
        tk.Label(brand, text="NEVO · REVISION", bg=INK, fg="white",
                 font=("Arial Narrow", 18, "bold")).pack(side="left",
                                                          padx=(12, 0))

        self.counter_lbl = tk.Label(
            head, text="", bg=INK, fg=MUTE, font=F_MONO_S)
        self.counter_lbl.pack(side="right", padx=24)

        # --- Banda explicativa -------------------------------------------
        info = tk.Frame(self, bg=CARD)
        info.pack(fill="x")
        tk.Label(
            info, bg=CARD, fg=DARK2, font=F_SANS,
            text="  Revisa solo los anunciantes marcados como dudosos. "
                 "Los demas pasan automaticamente al informe.",
            anchor="w", padx=24, pady=10
        ).pack(fill="x")

        # --- Cuerpo: dos columnas ----------------------------------------
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=20)

        left = tk.Frame(body, bg=BG, width=320)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        tk.Label(left, text="DUDOSOS", bg=BG, fg=MUTE,
                 font=F_MONO_B).pack(anchor="w")

        list_frame = tk.Frame(left, bg=BG, highlightbackground=LINE,
                               highlightthickness=1)
        list_frame.pack(fill="both", expand=True, pady=(8, 0))

        self.listbox = tk.Listbox(
            list_frame, bg=BG, fg=INK, font=F_SANS,
            selectbackground=INK, selectforeground="white",
            activestyle="none", relief="flat", borderwidth=0,
            highlightthickness=0)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_list_select)

        right = tk.Frame(body, bg=BG)
        right.pack(side="right", fill="both", expand=True, padx=(20, 0))

        self.detail = right
        self._build_detail()

        # --- Pie con CTA final -------------------------------------------
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", padx=24, pady=(0, 22))

        self.summary_lbl = tk.Label(
            foot, text="", bg=BG, fg=MUTE, font=F_MONO_S)
        self.summary_lbl.pack(side="left")

        tk.Button(
            foot, text="CANCELAR", command=self._on_close,
            bg=BG, fg=DARK2, font=F_SANS_B, relief="flat",
            activebackground=CARD, activeforeground=INK,
            cursor="hand2", padx=14, pady=8, borderwidth=0
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            foot, text="TERMINAR Y EXPORTAR", command=self._on_finish,
            bg=ACCENT, fg="white",
            font=("Arial Narrow", 12, "bold"), relief="flat",
            activebackground=DARK2, activeforeground="white",
            cursor="hand2", padx=18, pady=10, borderwidth=0
        ).pack(side="right")

    # ------------------------------------------------------------------ #
    def _build_detail(self):
        for w in self.detail.winfo_children():
            w.destroy()

        if not self.flagged:
            tk.Label(self.detail,
                     text="No hay anunciantes que revisar.",
                     bg=BG, fg=MUTE, font=F_SANS).pack(pady=80)
            return

        # Estado actual (chip)
        head = tk.Frame(self.detail, bg=BG)
        head.pack(fill="x")
        self.state_chip = tk.Label(
            head, text="PENDIENTE", bg=CARD, fg=DARK2,
            font=F_MONO_B, padx=10, pady=4)
        self.state_chip.pack(side="left")
        self.reason_lbl = tk.Label(
            head, text="", bg=BG, fg=MUTE, font=F_MONO_S)
        self.reason_lbl.pack(side="left", padx=12)

        # Imagen de la pagina
        self.img_canvas = tk.Label(
            self.detail, bg=CARD, fg=MUTE, font=F_MONO_S,
            text="(sin previa)")
        self.img_canvas.pack(fill="x", pady=(14, 14))

        # Campos editables
        form = tk.Frame(self.detail, bg=BG)
        form.pack(fill="x")

        self.fields = {}
        for i, (key, label) in enumerate([
            ("brand", "MARCA"),
            ("sector", "SECTOR"),
            ("website", "WEB"),
            ("email", "EMAIL"),
            ("phone", "TELEFONO"),
            ("ad_size", "TAMANO"),
        ]):
            row = i // 2
            col = i % 2
            cell = tk.Frame(form, bg=BG)
            cell.grid(row=row, column=col, sticky="nsew",
                       padx=(0, 12) if col == 0 else 0, pady=(0, 8))
            form.grid_columnconfigure(col, weight=1)
            tk.Label(cell, text=label, bg=BG, fg=MUTE,
                     font=F_MONO_S).pack(anchor="w")
            var = tk.StringVar()
            ent = tk.Entry(cell, textvariable=var, font=F_SANS,
                            bg="white", fg=INK, relief="flat",
                            highlightthickness=1,
                            highlightbackground=LINE,
                            highlightcolor=ACCENT,
                            insertbackground=INK)
            ent.pack(fill="x", ipady=6)
            self.fields[key] = var

        # Meta: paginas + confianza
        meta_row = tk.Frame(self.detail, bg=BG)
        meta_row.pack(fill="x", pady=(4, 12))
        self.meta_lbl = tk.Label(meta_row, text="", bg=BG, fg=MUTE,
                                  font=F_MONO_S)
        self.meta_lbl.pack(anchor="w")

        # Botonera de decision
        btns = tk.Frame(self.detail, bg=BG)
        btns.pack(fill="x", pady=(6, 0))

        tk.Button(
            btns, text="DESCARTAR", command=self._on_drop,
            bg=BG, fg=ACCENT, font=F_SANS_B, relief="flat",
            activebackground=CARD, activeforeground=ACCENT,
            cursor="hand2", padx=14, pady=10, borderwidth=1,
            highlightbackground=ACCENT, highlightthickness=1
        ).pack(side="left", expand=True, fill="x", padx=(0, 6))

        tk.Button(
            btns, text="CONFIRMAR", command=self._on_keep,
            bg=INK, fg="white",
            font=("Arial Narrow", 12, "bold"), relief="flat",
            activebackground=DARK2, activeforeground="white",
            cursor="hand2", padx=14, pady=10, borderwidth=0
        ).pack(side="left", expand=True, fill="x", padx=(6, 0))

    # ------------------------------------------------------------------ #
    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for i, a in enumerate(self.flagged):
            mark = {"pending": "·", "keep": "✓", "drop": "✕"}[self.states[i]]
            page = a.pages[0] if a.pages else "-"
            text = f" {mark}  {a.brand[:28]:<28}  p.{page}"
            self.listbox.insert("end", text)
            # color del estado
            self.listbox.itemconfig(i, fg=self.STATE_COLOR[self.states[i]])
        if self.flagged:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(self.idx)
            self.listbox.see(self.idx)

        n = len(self.flagged)
        kept = sum(1 for s in self.states if s == self.STATE_KEEP)
        dropped = sum(1 for s in self.states if s == self.STATE_DROP)
        pending = n - kept - dropped
        self.counter_lbl.config(
            text=f"{self.idx + 1 if self.flagged else 0} / {n}")
        self.summary_lbl.config(
            text=f"CONFIRMADOS {kept}   ·   DESCARTADOS {dropped}   "
                 f"·   PENDIENTES {pending}")

    # ------------------------------------------------------------------ #
    def _show(self, i: int):
        if not self.flagged or not (0 <= i < len(self.flagged)):
            return
        # Guardar las ediciones del que dejamos antes de cambiar
        if hasattr(self, "_current_idx"):
            self._save_edits(self._current_idx)

        self.idx = i
        self._current_idx = i
        a = self.flagged[i]

        # Chip de estado
        st = self.states[i]
        self.state_chip.config(
            text=self.STATE_LABEL[st],
            fg="white" if st != self.STATE_PENDING else DARK2,
            bg=self.STATE_COLOR[st] if st != self.STATE_PENDING else CARD)

        self.reason_lbl.config(text=review_flag_label(a.review_flag))

        # Cargar imagen de la primera pagina del anunciante
        page_num = a.pages[0] if a.pages else None
        self._load_preview(page_num)

        # Rellenar campos
        for key, var in self.fields.items():
            var.set(getattr(a, key, "") or "")

        # Meta
        self.meta_lbl.config(
            text=f"PAGINAS: {', '.join(str(p) for p in a.pages) or '—'}"
                 f"     ·     CONFIANZA: {a.confidence:.0%}"
                 f"     ·     METODO: {a.method.upper()}")

        self._refresh_list()

    def _save_edits(self, i: int):
        if not (0 <= i < len(self.flagged)):
            return
        a = self.flagged[i]
        for key, var in self.fields.items():
            setattr(a, key, var.get().strip())

    # ------------------------------------------------------------------ #
    def _load_preview(self, page_num):
        if page_num is None or not PIL_TK:
            self.img_canvas.config(image="", text="(sin previa)",
                                    width=60, height=14)
            return
        page = self.pages_by_num.get(page_num)
        if not page or not os.path.exists(page.image_path):
            self.img_canvas.config(image="", text="(imagen no disponible)",
                                    width=60, height=14)
            return
        if page_num in self._img_cache:
            self.img_canvas.config(image=self._img_cache[page_num], text="")
            return
        try:
            img = Image.open(page.image_path)
            # Cabe en ~750 x 380 para no robar espacio al formulario.
            img.thumbnail((760, 380), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._img_cache[page_num] = photo
            self.img_canvas.config(image=photo, text="")
        except Exception as e:  # noqa: BLE001
            self.img_canvas.config(image="",
                                    text=f"(error cargando imagen: {e})")

    # ------------------------------------------------------------------ #
    def _on_list_select(self, _evt):
        sel = self.listbox.curselection()
        if sel:
            self._show(sel[0])

    def _on_keep(self):
        self.states[self.idx] = self.STATE_KEEP
        self._save_edits(self.idx)
        self._advance()

    def _on_drop(self):
        self.states[self.idx] = self.STATE_DROP
        self._advance()

    def _advance(self):
        nxt = self.idx + 1
        if nxt < len(self.flagged):
            self._show(nxt)
        else:
            self._refresh_list()

    # ------------------------------------------------------------------ #
    def _on_finish(self):
        if hasattr(self, "_current_idx"):
            self._save_edits(self._current_idx)
        kept = list(self.non_flagged)
        for i, a in enumerate(self.flagged):
            if self.states[i] != self.STATE_DROP:
                kept.append(a)
        # Orden estable: por confianza descendente, luego marca.
        kept.sort(key=lambda x: (-x.confidence, x.brand.lower()))
        self.grab_release()
        self.destroy()
        self.on_done(kept)

    def _on_close(self):
        if messagebox.askyesno(
                "Cancelar revision",
                "Si cancelas, el informe se generara con la lista completa "
                "sin tus cambios. Continuar?"):
            self.grab_release()
            self.destroy()
            # Aplicar la lista original sin ediciones.
            self.on_done(self.all_advertisers)


class LibraryWindow(tk.Toplevel):
    """Biblioteca de revistas analizadas: listar, comparar dos numeros y
    abrir el historico de un anunciante."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("NEVO · Biblioteca de revistas")
        self.configure(bg=BG)
        self.geometry("760x560")
        self.transient(parent)

        from core.library import Library
        self.lib = Library()
        self.issues = self.lib.list_issues()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # Cabecera
        head = tk.Frame(self, bg=INK)
        head.pack(fill="x")
        tk.Label(head, text="BIBLIOTECA", bg=INK, fg="white",
                 font=("Arial Narrow", 18, "bold")).pack(side="left",
                                                          padx=24, pady=16)
        tk.Label(head, text=f"{len(self.issues)} numero(s) guardado(s)",
                 bg=INK, fg=MUTE, font=F_MONO_S).pack(side="right", padx=24)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=18)

        if not self.issues:
            tk.Label(body, text="Aun no hay revistas guardadas.\n"
                     "Analiza una revista y se guardara aqui "
                     "automaticamente.",
                     bg=BG, fg=MUTE, font=F_SANS, justify="center").pack(
                         pady=80)
            return

        tk.Label(body, text="Selecciona DOS numeros para comparar "
                 "(A = anterior, B = actual)", bg=BG, fg=INK,
                 font=F_MONO_B).pack(anchor="w")

        list_frame = tk.Frame(body, bg=BG)
        list_frame.pack(fill="both", expand=True, pady=(8, 12))
        self.listbox = tk.Listbox(list_frame, bg=CARD, fg=INK,
                                  font=F_MONO, relief="flat",
                                  selectmode="multiple",
                                  selectbackground=ACCENT,
                                  selectforeground="white",
                                  borderwidth=0, highlightthickness=0,
                                  activestyle="none")
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        for it in self.issues:
            fecha = (it.get("fecha_analisis", "") or "")[:16].replace("T", " ")
            num = it.get("numero", "") or "?"
            titulo = it.get("titulo", "Revista") or "Revista"
            n = it.get("n_anunciantes", 0)
            self.listbox.insert(
                "end", f"  #{num:<6} {titulo:<26} {n:>3} anunc.  {fecha}")

        btn_row = tk.Frame(body, bg=BG)
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="COMPARAR SELECCIONADOS",
                  command=self._compare, bg=ACCENT, fg="white",
                  activebackground=DARK2, activeforeground="white",
                  relief="flat", font=("Arial Narrow", 12, "bold"),
                  cursor="hand2", pady=10, borderwidth=0).pack(
                      side="left", fill="x", expand=True)
        tk.Button(btn_row, text="VER ANUNCIANTES",
                  command=self._show_advertisers, bg=BG, fg=INK,
                  activebackground=CARD, relief="flat", font=F_MONO_B,
                  cursor="hand2", pady=10, borderwidth=1,
                  highlightbackground=LINE, highlightthickness=1).pack(
                      side="left", padx=(10, 0))

    def _selected_ids(self) -> list[int]:
        return [self.issues[i]["id"] for i in self.listbox.curselection()]

    def _compare(self):
        sel = self.listbox.curselection()
        if len(sel) != 2:
            messagebox.showinfo(
                "Comparar", "Selecciona exactamente DOS numeros "
                "(manten Cmd/Ctrl para elegir el segundo).", parent=self)
            return
        # El mas antiguo es A, el mas reciente es B (las filas vienen
        # ordenadas de mas reciente a mas antiguo).
        i_recent, i_old = min(sel), max(sel)
        id_b = self.issues[i_recent]["id"]
        id_a = self.issues[i_old]["id"]
        try:
            cmp = self.lib.compare_issues(id_a, id_b)
            from core.compare_report import export_comparison_html
            outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "output")
            os.makedirs(outdir, exist_ok=True)
            import datetime
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
            path = os.path.join(outdir, f"comparativa_{stamp}.html")
            export_comparison_html(cmp, path)
            webbrowser.open(f"file://{os.path.abspath(path)}")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Comparar",
                                 f"No se pudo comparar: {e}", parent=self)

    def _show_advertisers(self):
        ids = self._selected_ids()
        if len(ids) != 1:
            messagebox.showinfo(
                "Ver anunciantes",
                "Selecciona UN solo numero para ver sus anunciantes.",
                parent=self)
            return
        ads = self.lib.get_advertisers(ids[0])
        issue = self.lib.get_issue(ids[0])
        lines = [f"{a['brand']}  ({a.get('sector') or 's/sector'})"
                 for a in ads]
        messagebox.showinfo(
            f"#{issue.get('numero','?')} · {len(ads)} anunciantes",
            "\n".join(lines) if lines else "Sin anunciantes.",
            parent=self)

    def _on_close(self):
        try:
            self.lib.close()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
