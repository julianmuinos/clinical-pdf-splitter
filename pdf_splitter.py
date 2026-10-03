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
# Formato: "Módulo: <prefijo> <número_hc>"
#
# Prefijos de módulo conocidos (capturados por \S+):
#   NM0, NM1, NM2, NM3, NM4, NM5, NM10, NM1A, NM5B, NM9A
#
# Formatos de número de historia clínica soportados:
#   - Solo dígitos (1-4):     79, 102, 990, 1710
#   - 1 letra + 3-4 dígitos:  P050, D0004, F0001
#   - 2 letras + 4 dígitos:   GE1347, PR0019
#   - 3 letras + 3 dígitos:   GEP086
_REGEX_MODULO = re.compile(
    r"m\S{2,6}o\s*:\s*(\S+)\s+([A-Za-z]*\d+)",
    re.IGNORECASE,
)

# Regex para "Código paciente:" y variantes abreviadas con alta tolerancia OCR.
# Soporta: Código paciente, Codigo paciente, COD. PACIENTE,
#          CÓD. PACIENTE, có. paciente (OCR pierde la 'd'),
#          c?b. paciente / c?p. paciente (OCR corrompe el acento y/o la 'd').
# Se usa un patrón permisivo [^\s]{0,4} entre 'c' y 'paciente' para absorber
# cualquier secuencia de ruido OCR corta (máx. 4 chars no-espacio).
_REGEX_CODIGO_PACIENTE = re.compile(
    r"c[^\s]{0,4}\.?\s+paciente\s*:\s*(\S+)",
    re.IGNORECASE,
)

# Regex para "Paciente: XXXX" — formato alternativo que aparece en remitos,
# recetas y otros documentos vinculados a la historia clínica.
# Ej: "Paciente: MNICH25021988" (iniciales del paciente + fecha de nacimiento).
# El código tiene formato: 2-6 letras + 6-12 dígitos.
# Solo aplica al inicio de línea (re.MULTILINE) para evitar falsos positivos.
_REGEX_PACIENTE_SOLO = re.compile(
    r"^paciente\s*:\s*([A-Za-z]{2,6}\d{6,12})",
    re.IGNORECASE | re.MULTILINE,
)


def extraer_identificadores(texto: str) -> tuple[Optional[str], Optional[str]]:
    """Extrae de forma independiente ambos identificadores presentes en la página.

    A diferencia de :func:`detectar_codigo`, no prioriza uno sobre el otro:
    extrae el número del módulo Y el código largo del paciente por separado,
    lo que permite construir referencias cruzadas entre ambos.

    Args:
        texto: Texto OCR de la página.

    Returns:
        Tupla ``(codigo_modulo, codigo_paciente_largo)`` donde:

        - ``codigo_modulo``: número de historia clínica extraído del campo
          'Módulo:' (ej. ``"990"``), o ``None`` si no se encontró.
        - ``codigo_paciente_largo``: código alfanumérico largo proveniente
          de 'cód. paciente:' o 'Paciente:' (ej. ``"MHUBR17121943"``),
          o ``None`` si no se encontró.
    """
    codigo_modulo: Optional[str] = None
    codigo_paciente: Optional[str] = None

    # Intentar detectar número de módulo (identificador principal de HC)
    match_modulo = _REGEX_MODULO.search(texto)
    if match_modulo:
        codigo_modulo = match_modulo.group(2).upper()

    # Intentar detectar código largo del paciente
    # Primero por "cód. paciente:" (en páginas de HC con encabezado)
    match_cod = _REGEX_CODIGO_PACIENTE.search(texto)
    if match_cod:
        codigo_paciente = match_cod.group(1).strip().upper()
    else:
        # Luego por "Paciente:" (en remitos, recetas y documentos adjuntos)
        match_pac = _REGEX_PACIENTE_SOLO.search(texto)
        if match_pac:
            codigo_paciente = match_pac.group(1).strip().upper()

    return codigo_modulo, codigo_paciente


def detectar_codigo(texto: str) -> Optional[str]:
    """Detecta el código del paciente a partir del texto OCR de una página.

    Wrapper de compatibilidad sobre :func:`extraer_identificadores`.
    Prioriza el número del módulo (identificador primario de HC); si no está
    disponible, devuelve el código largo del paciente.

    Args:
        texto: Texto OCR de la página.

    Returns:
        El código identificador del paciente o None si no se encontró
        ningún patrón.
    """
    codigo_modulo, codigo_paciente = extraer_identificadores(texto)
    return codigo_modulo or codigo_paciente


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

    Implementa un algoritmo de **dos pasadas**:

    1. **Pasada OCR**: renderiza y aplica OCR a todas las páginas, almacena
       los textos en memoria y construye un mapa de referencias cruzadas
       ``{código_largo_paciente → número_módulo}`` a partir de las páginas
       que contienen ambos campos simultáneamente (encabezado de HC completo).

    2. **Pasada de agrupación**: recorre los textos cacheados y determina el
       código efectivo de cada página mediante la siguiente prioridad:

       1. Número de módulo detectado directamente en la página.
       2. Código largo resuelto vía el mapa (ej. página de remito con solo
          ``Paciente: MHUBR17121943`` → resuelve a módulo ``990``).
       3. Código largo sin resolver (cuando no existe módulo correspondiente).
       4. Último paciente detectado (páginas totalmente sin identificador).

    Args:
        ruta_pdf: Ruta al archivo PDF de entrada.
        carpeta_salida: Ruta a la carpeta donde se guardarán los PDFs separados.
        callback_progreso: Función callback(paso_actual, total_pasos) para
            actualizar la barra de progreso (total_pasos = total_paginas × 2).
        callback_log: Función callback(mensaje) para enviar mensajes de log.

    Returns:
        Diccionario con estadísticas del procesamiento::

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
    # El progreso se distribuye en dos pasadas de igual peso
    total_pasos = total_paginas * 2
    log(f"Total de páginas: {total_paginas}")

    reader = PdfReader(ruta_pdf)

    # ---------------------------------------------------------------------------
    # Pasada 1: Extracción OCR y construcción del mapa de referencias cruzadas
    # ---------------------------------------------------------------------------
    # mapa_cod_largo_a_modulo vincula el código largo del paciente
    # (campo "cód. paciente:" o "Paciente:") con el número del módulo
    # (campo "Módulo: NMx NNNN"), extraídos de páginas que contienen ambos.
    # Ejemplo: {"MHUBR17121943": "990"}
    # ---------------------------------------------------------------------------
    log("\n── Pasada 1/2: Extracción OCR y construcción de referencias cruzadas ──")
    textos_paginas: list[str] = []
    mapa_cod_largo_a_modulo: dict[str, str] = {}

    try:
        for i in range(total_paginas):
            num_pagina = i + 1
            log(f"\n  [OCR] Página {num_pagina}/{total_paginas}")

            # Renderizar página a imagen (300 DPI)
            pagina = pdf_doc[i]
            imagen = pagina.render(scale=300 / 72).to_pil()

            # Aplicar OCR y cachear texto
            texto = extraer_texto_pagina(imagen)
            textos_paginas.append(texto)
            log(f"  Texto extraído ({len(texto)} caracteres)")

            codigo_modulo, codigo_paciente = extraer_identificadores(texto)

            if codigo_modulo and codigo_paciente:
                # Página con encabezado completo → registrar referencia cruzada
                mapa_cod_largo_a_modulo[codigo_paciente] = codigo_modulo
                log(f"  ↔ Referencia cruzada: {codigo_paciente} → módulo {codigo_modulo}")
            elif codigo_modulo:
                log(f"  ✔ Módulo detectado: {codigo_modulo}")
            elif codigo_paciente:
                log(f"  ~ Código de paciente sin módulo: {codigo_paciente}")
            else:
                log("  - Sin identificadores en esta página")

            if callback_progreso:
                callback_progreso(num_pagina, total_pasos)
    finally:
        pdf_doc.close()

    log(f"\n  Referencias cruzadas construidas: {len(mapa_cod_largo_a_modulo)}")
    for cod, mod in mapa_cod_largo_a_modulo.items():
        log(f"    {cod} → {mod}")

    # ---------------------------------------------------------------------------
    # Pasada 2: Agrupación de páginas por paciente
    # ---------------------------------------------------------------------------
    log("\n── Pasada 2/2: Agrupación de páginas por paciente ──")
    grupos: list[tuple[str, list[int]]] = []
    codigo_actual: Optional[str] = None
    paginas_sin_codigo = 0

    for i, texto in enumerate(textos_paginas):
        num_pagina = i + 1
        log(f"\n--- Página {num_pagina}/{total_paginas} ---")

        codigo_modulo, codigo_paciente = extraer_identificadores(texto)

        # Determinar el código efectivo de agrupación según la prioridad:
        # 1) número de módulo  2) cód. largo resuelto  3) cód. largo sin resolver
        codigo_efectivo: Optional[str] = None

        if codigo_modulo:
            codigo_efectivo = codigo_modulo
            log(f"  ✔ Código de módulo: {codigo_modulo}")
        elif codigo_paciente:
            if codigo_paciente in mapa_cod_largo_a_modulo:
                codigo_efectivo = mapa_cod_largo_a_modulo[codigo_paciente]
                log(f"  ✔ Código resuelto: {codigo_paciente} → módulo {codigo_efectivo}")
            else:
                codigo_efectivo = codigo_paciente
                log(f"  ✔ Código de paciente (sin módulo correspondiente): {codigo_paciente}")

        if codigo_efectivo:
            if codigo_efectivo != codigo_actual:
                # Nuevo paciente detectado
                codigo_actual = codigo_efectivo
                grupos.append((codigo_efectivo, [i]))
                log(f"  → Nuevo paciente: {codigo_efectivo}")
            else:
                # Continuación del paciente actual
                grupos[-1][1].append(i)
                log(f"  → Continuación del paciente: {codigo_efectivo}")
        else:
            log("  ✖ No se detectó código en esta página")
            paginas_sin_codigo += 1
            if grupos:
                # Asignar al último paciente conocido
                grupos[-1][1].append(i)
                log(f"  → Asignada al paciente actual: {grupos[-1][0]}")
            else:
                # Primera(s) página(s) sin código — crear grupo temporal
                grupos.append(("SIN_CODIGO", [i]))
                log("  → Asignada a grupo 'SIN_CODIGO' (inicio del PDF)")

        if callback_progreso:
            callback_progreso(total_paginas + num_pagina, total_pasos)

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

