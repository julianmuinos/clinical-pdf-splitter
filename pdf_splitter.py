"""
Separador de Historias Clínicas PDF
====================================
Programa que toma un PDF escaneado con historias clínicas de múltiples pacientes
y lo separa en archivos PDF individuales por paciente, utilizando OCR (Tesseract)
para detectar los códigos identificatorios.

Requisitos:
    - Python 3.7+
    - Tesseract OCR instalado en el sistema
    - Dependencias Python: pytesseract, pypdfium2, PyPDF2, Pillow
"""

import os
import re
import sys
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import pypdfium2 as pdfium
import pytesseract
from PyPDF2 import PdfReader, PdfWriter


# ---------------------------------------------------------------------------
# Configuración de OCR
# ---------------------------------------------------------------------------

# Directorio base de la aplicación (funciona tanto en script como en ejecutable congelado)
if getattr(sys, "frozen", False):
    _APP_DIR = os.path.dirname(sys.executable)
    _INTERNAL_DIR = getattr(sys, "_MEIPASS", os.path.join(_APP_DIR, "_internal"))
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
    _INTERNAL_DIR = _APP_DIR

# Auto-detectar ruta de Tesseract (prioriza la versión local empaquetada)
tesseract_rutas_comunes = [
    os.path.join(_APP_DIR, "tesseract", "tesseract.exe"),
    os.path.join(_INTERNAL_DIR, "tesseract", "tesseract.exe"),
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
]

for ruta in tesseract_rutas_comunes:
    if os.path.exists(ruta):
        pytesseract.pytesseract.tesseract_cmd = ruta
        # Si tiene carpeta tessdata adyacente, fijar TESSDATA_PREFIX
        tessdata_local = os.path.join(os.path.dirname(ruta), "tessdata")
        if os.path.exists(tessdata_local):
            os.environ["TESSDATA_PREFIX"] = tessdata_local
        print(f"[OCR] Tesseract configurado: {ruta}")
        if "TESSDATA_PREFIX" in os.environ:
            print(f"[OCR] TESSDATA_PREFIX: {os.environ['TESSDATA_PREFIX']}")
        break



# ---------------------------------------------------------------------------
# Módulo de extracción de texto (OCR)
# ---------------------------------------------------------------------------

def extraer_texto_pagina(imagen) -> str:
    """Aplica OCR sobre una imagen de página y retorna el texto extraído.

    Args:
        imagen: Objeto PIL.Image de la página.

    Returns:
        Texto extraído de la imagen.
    """
    texto = pytesseract.image_to_string(imagen, lang="spa")
    return texto


# ---------------------------------------------------------------------------
# Módulo de detección de códigos
# ---------------------------------------------------------------------------

# Regex tolerante a errores severos de OCR en la palabra "Módulo".
# El OCR puede producir variantes como: módulo, modulo, móbuio, moóduio, etc.
# El patrón m\S{2,6}o matchea cualquier palabra de 4-8 caracteres que empiece
# con 'm' y termine con 'o', seguida de ':'.
#
# Formato: "Módulo: <prefijo> <código_paciente>"
#
# Prefijos de módulo conocidos (capturados por \S+):
#   NM0, NM1, NM2, NM3, NM4, NM5, NM10, NM1A, NM5B, NM9A
#
# Formatos de código de paciente soportados:
#   - Solo dígitos (1-4):     79, 102, 1710
#   - 1 letra + 3-4 dígitos:  P050, D0004, F0001
#   - 2 letras + 4 dígitos:   GE1347, PR0019
#   - 3 letras + 3 dígitos:   GEP086
_REGEX_MODULO = re.compile(
    r"m\S{2,6}o\s*:\s*(\S+)\s+([A-Za-z]*\d+)",
    re.IGNORECASE,
)

# Regex para "Código paciente:" y variantes abreviadas.
# Soporta: Código paciente, Codigo paciente, COD. PACIENTE,
#          CÓD. PACIENTE, có. paciente (OCR pierde la 'd'), cod paciente, etc.
_REGEX_CODIGO_PACIENTE = re.compile(
    r"c[óoÓO]d?(?:igo)?\.?\s+paciente\s*:\s*(\S+)",
    re.IGNORECASE,
)


def detectar_codigo(texto: str) -> Optional[str]:
    """Detecta el código del paciente a partir del texto OCR de una página.

    Busca primero el patrón 'Módulo: XXXX <código>' (tolerante a corrupciones
    OCR severas de la palabra "Módulo") y extrae la segunda parte.
    Formatos de código reconocidos: GE0558, PR0019, GEP086, D0004, P050, 1710, 102, 79.

    Si no lo encuentra, intenta con 'Código paciente: XXXX' y variantes
    abreviadas como 'COD. PACIENTE:', 'CÓD. PACIENTE:', 'có. paciente:'.

    Args:
        texto: Texto OCR de la página.

    Returns:
        El código identificador del paciente o None si no se encontró
        ningún patrón.
    """
    # Intentar detectar por módulo
    match_modulo = _REGEX_MODULO.search(texto)
    if match_modulo:
        codigo_modulo = match_modulo.group(2).upper()
        return codigo_modulo

    # Intentar detectar por código paciente
    match_paciente = _REGEX_CODIGO_PACIENTE.search(texto)
    if match_paciente:
        codigo_paciente = match_paciente.group(1).strip()
        return codigo_paciente

    return None


# ---------------------------------------------------------------------------
# Módulo de división de PDF
# ---------------------------------------------------------------------------

def dividir_pdf(
    ruta_pdf: str,
    carpeta_salida: str,
    callback_progreso=None,
    callback_log=None,
) -> dict:
    """Divide un PDF escaneado en archivos individuales por paciente.

    Args:
        ruta_pdf: Ruta al archivo PDF de entrada.
        carpeta_salida: Ruta a la carpeta donde se guardarán los PDFs separados.
        callback_progreso: Función callback(pagina_actual, total_paginas) para
            actualizar la barra de progreso.
        callback_log: Función callback(mensaje) para enviar mensajes de log.

    Returns:
        Diccionario con estadísticas del procesamiento:
        {
            "total_paginas": int,
            "pacientes_encontrados": int,
            "archivos_generados": list[str],
            "paginas_sin_codigo": int,
        }
    """

    def log(msg: str):
        if callback_log:
            callback_log(msg)

    log(f"Abriendo PDF: {os.path.basename(ruta_pdf)}")

    # Abrir el PDF con pypdfium2 para renderizado y PyPDF2 para manipulación
    pdf_doc = pdfium.PdfDocument(ruta_pdf)
    total_paginas = len(pdf_doc)
    log(f"Total de páginas: {total_paginas}")

    reader = PdfReader(ruta_pdf)

    # Estructura para agrupar páginas por paciente
    # Lista de tuplas: (codigo_paciente, [indices_de_paginas])
    grupos: list[tuple[str, list[int]]] = []
    codigo_actual: Optional[str] = None
    paginas_sin_codigo = 0

    try:
        # Procesar cada página una a una (ahorra memoria y procesa al instante)
        for i in range(total_paginas):
            num_pagina = i + 1
            log(f"\n--- Página {num_pagina}/{total_paginas} ---")

            # Renderizar página a imagen (300 DPI)
            pagina = pdf_doc[i]
            imagen = pagina.render(scale=300 / 72).to_pil()

            # Aplicar OCR
            texto = extraer_texto_pagina(imagen)
            log(f"  Texto OCR extraído ({len(texto)} caracteres)")

            # Detectar código
            codigo = detectar_codigo(texto)

            if codigo:
                log(f"  ✔ Código detectado: {codigo}")
                if codigo != codigo_actual:
                    # Nuevo paciente encontrado
                    codigo_actual = codigo
                    grupos.append((codigo, [i]))
                    log(f"  → Nuevo paciente: {codigo}")
                else:
                    # Misma persona, agregar página al grupo actual
                    grupos[-1][1].append(i)
            else:
                log("  ✖ No se detectó código en esta página")
                paginas_sin_codigo += 1
                if grupos:
                    # Asignar al último paciente
                    grupos[-1][1].append(i)
                    log(f"  → Asignada al paciente actual: {grupos[-1][0]}")
                else:
                    # Primera(s) página(s) sin código — crear grupo temporal
                    if not grupos:
                        grupos.append(("SIN_CODIGO", [i]))
                        log("  → Asignada a grupo 'SIN_CODIGO' (inicio del PDF)")

            # Actualizar progreso
            if callback_progreso:
                callback_progreso(num_pagina, total_paginas)
    finally:
        pdf_doc.close()

    # Generar PDFs de salida
    log(f"\n{'='*50}")
    log("Generando archivos PDF de salida...")

    archivos_generados = []
    os.makedirs(carpeta_salida, exist_ok=True)

    for codigo, indices in grupos:
        writer = PdfWriter()
        for idx in indices:
            writer.add_page(reader.pages[idx])

        # Manejar nombres duplicados
        nombre_base = codigo
        nombre_archivo = f"{nombre_base}.pdf"
        ruta_salida = os.path.join(carpeta_salida, nombre_archivo)

        # Si ya existe, agregar sufijo numérico
        contador = 1
        while os.path.exists(ruta_salida):
            nombre_archivo = f"{nombre_base}_{contador}.pdf"
            ruta_salida = os.path.join(carpeta_salida, nombre_archivo)
            contador += 1

        with open(ruta_salida, "wb") as f:
            writer.write(f)

        archivos_generados.append(nombre_archivo)
        log(f"  ✔ {nombre_archivo} ({len(indices)} página{'s' if len(indices) > 1 else ''})")

    log(f"\n{'='*50}")
    log("¡Proceso completo!")
    log(f"  Pacientes encontrados: {len(grupos)}")
    log(f"  Archivos generados: {len(archivos_generados)}")
    log(f"  Páginas sin código: {paginas_sin_codigo}")

    return {
        "total_paginas": total_paginas,
        "pacientes_encontrados": len(grupos),
        "archivos_generados": archivos_generados,
        "paginas_sin_codigo": paginas_sin_codigo,
    }


# ---------------------------------------------------------------------------
# Interfaz Gráfica (GUI)
# ---------------------------------------------------------------------------

class AplicacionSeparadorPDF:
    """Interfaz gráfica para el separador de historias clínicas PDF."""

    def __init__(self):
        self.ventana = tk.Tk()
        self.ventana.title("Separador de Historias Clínicas PDF")
        self.ventana.geometry("700x550")
        self.ventana.resizable(True, True)
        self.ventana.minsize(600, 450)

        # Cargar ícono de la ventana si está disponible
        for icon_candidate in [
            os.path.join(_APP_DIR, "assets", "icon.ico"),
            os.path.join(_INTERNAL_DIR, "assets", "icon.ico"),
            os.path.join(_APP_DIR, "icon.ico"),
        ]:
            if os.path.exists(icon_candidate):
                try:
                    self.ventana.iconbitmap(icon_candidate)
                    break
                except Exception:
                    pass

        self.ruta_pdf = tk.StringVar(value="")
        self.ruta_salida = tk.StringVar(value="")
        self.procesando = False

        self._crear_widgets()

    def _crear_widgets(self):
        """Crea todos los widgets de la interfaz."""
        # Frame principal con padding
        frame_principal = ttk.Frame(self.ventana, padding=15)
        frame_principal.pack(fill=tk.BOTH, expand=True)

        # --- Título ---
        ttk.Label(
            frame_principal,
            text="Separador de Historias Clínicas PDF",
            font=("Segoe UI", 14, "bold"),
        ).pack(pady=(0, 15))

        # --- Selección de PDF ---
        frame_pdf = ttk.LabelFrame(frame_principal, text="Archivo PDF de entrada", padding=10)
        frame_pdf.pack(fill=tk.X, pady=(0, 10))

        frame_pdf_row = ttk.Frame(frame_pdf)
        frame_pdf_row.pack(fill=tk.X)

        ttk.Button(
            frame_pdf_row,
            text="Seleccionar PDF...",
            command=self._seleccionar_pdf,
        ).pack(side=tk.LEFT)

        ttk.Label(
            frame_pdf_row,
            textvariable=self.ruta_pdf,
            wraplength=500,
            foreground="gray",
        ).pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)

        # --- Selección de carpeta de salida ---
        frame_salida = ttk.LabelFrame(frame_principal, text="Carpeta de salida", padding=10)
        frame_salida.pack(fill=tk.X, pady=(0, 10))

        frame_salida_row = ttk.Frame(frame_salida)
        frame_salida_row.pack(fill=tk.X)

        ttk.Button(
            frame_salida_row,
            text="Seleccionar carpeta...",
            command=self._seleccionar_carpeta,
        ).pack(side=tk.LEFT)

        ttk.Label(
            frame_salida_row,
            textvariable=self.ruta_salida,
            wraplength=500,
            foreground="gray",
        ).pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)

        # --- Botón Procesar ---
        self.btn_procesar = ttk.Button(
            frame_principal,
            text="▶  Procesar",
            command=self._iniciar_procesamiento,
        )
        self.btn_procesar.pack(pady=10)

        # --- Barra de progreso ---
        self.barra_progreso = ttk.Progressbar(
            frame_principal,
            mode="determinate",
            length=400,
        )
        self.barra_progreso.pack(fill=tk.X, pady=(0, 10))

        self.label_progreso = ttk.Label(
            frame_principal,
            text="",
            foreground="gray",
        )
        self.label_progreso.pack()

        # --- Área de log ---
        frame_log = ttk.LabelFrame(frame_principal, text="Log del proceso", padding=5)
        frame_log.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.texto_log = tk.Text(
            frame_log,
            height=12,
            state=tk.DISABLED,
            font=("Consolas", 9),
            wrap=tk.WORD,
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
        )
        self.texto_log.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        scrollbar = ttk.Scrollbar(frame_log, command=self.texto_log.yview)
        scrollbar.pack(fill=tk.Y, side=tk.RIGHT)
        self.texto_log.configure(yscrollcommand=scrollbar.set)

    def _seleccionar_pdf(self):
        """Abre diálogo para seleccionar el archivo PDF de entrada."""
        ruta = filedialog.askopenfilename(
            title="Seleccionar PDF de historias clínicas",
            filetypes=[("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")],
        )
        if ruta:
            self.ruta_pdf.set(ruta)
            # Sugerir carpeta de salida si no hay una seleccionada
            if not self.ruta_salida.get():
                carpeta_sugerida = os.path.join(os.path.dirname(ruta), "Pacientes_Separados")
                self.ruta_salida.set(carpeta_sugerida)

    def _seleccionar_carpeta(self):
        """Abre diálogo para seleccionar la carpeta de salida."""
        ruta = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if ruta:
            self.ruta_salida.set(ruta)

    def _agregar_log(self, mensaje: str):
        """Agrega un mensaje al área de log (thread-safe)."""
        def _insertar():
            self.texto_log.configure(state=tk.NORMAL)
            self.texto_log.insert(tk.END, mensaje + "\n")
            self.texto_log.see(tk.END)
            self.texto_log.configure(state=tk.DISABLED)

        self.ventana.after(0, _insertar)

    def _actualizar_progreso(self, actual: int, total: int):
        """Actualiza la barra de progreso (thread-safe)."""
        def _actualizar():
            porcentaje = (actual / total) * 100
            self.barra_progreso["value"] = porcentaje
            self.label_progreso.configure(
                text=f"Página {actual} de {total} ({porcentaje:.0f}%)"
            )

        self.ventana.after(0, _actualizar)

    def _iniciar_procesamiento(self):
        """Valida las entradas e inicia el procesamiento en un hilo separado."""
        if self.procesando:
            return

        ruta_pdf = self.ruta_pdf.get()
        ruta_salida = self.ruta_salida.get()

        if not ruta_pdf:
            messagebox.showwarning("Atención", "Seleccioná un archivo PDF primero.")
            return

        if not os.path.isfile(ruta_pdf):
            messagebox.showerror("Error", f"El archivo no existe:\n{ruta_pdf}")
            return

        if not ruta_salida:
            messagebox.showwarning("Atención", "Seleccioná una carpeta de salida.")
            return

        # Limpiar log y progreso
        self.texto_log.configure(state=tk.NORMAL)
        self.texto_log.delete("1.0", tk.END)
        self.texto_log.configure(state=tk.DISABLED)
        self.barra_progreso["value"] = 0
        self.label_progreso.configure(text="Iniciando...")

        # Deshabilitar botón
        self.procesando = True
        self.btn_procesar.configure(state=tk.DISABLED)

        # Ejecutar en hilo separado
        hilo = threading.Thread(
            target=self._procesar_en_hilo,
            args=(ruta_pdf, ruta_salida),
            daemon=True,
        )
        hilo.start()

    def _procesar_en_hilo(self, ruta_pdf: str, ruta_salida: str):
        """Ejecuta el procesamiento en un hilo separado para no bloquear la GUI."""
        try:
            resultado = dividir_pdf(
                ruta_pdf=ruta_pdf,
                carpeta_salida=ruta_salida,
                callback_progreso=self._actualizar_progreso,
                callback_log=self._agregar_log,
            )

            # Mostrar mensaje de éxito
            res_generados = list(resultado["archivos_generados"])

            def _exito():
                self.label_progreso.configure(text="¡Proceso completado!")
                messagebox.showinfo(
                    "Proceso Completo",
                    f"Se generaron {len(res_generados)} archivos PDF\n"
                    f"en la carpeta:\n{ruta_salida}",
                )

            self.ventana.after(0, _exito)

        except Exception as exc:
            mensaje_error = str(exc)
            traza_error = traceback.format_exc()

            def _error(msg=mensaje_error, traza=traza_error):
                self.label_progreso.configure(text="Error durante el proceso")
                messagebox.showerror("Error", f"Ocurrió un error:\n{msg}")
                self._agregar_log(f"\n❌ ERROR: {msg}\n{traza}")

            self.ventana.after(0, _error)

        finally:
            def _finalizar():
                self.procesando = False
                self.btn_procesar.configure(state=tk.NORMAL)

            self.ventana.after(0, _finalizar)

    def ejecutar(self):
        """Inicia el loop principal de la GUI."""
        self.ventana.mainloop()


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = AplicacionSeparadorPDF()
    app.ejecutar()

