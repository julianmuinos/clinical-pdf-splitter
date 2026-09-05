# Clinical PDF Splitter ????

Herramienta de escritorio en Python con interfaz gráfica para dividir archivos PDF escaneados que contienen múltiples historias clínicas o estudios médicos, separándolos en documentos individuales por paciente mediante **OCR** (Reconocimiento Óptico de Caracteres).

---

## ?? Características principales

- **Procesamiento de PDFs escaneados:** Renderiza páginas a alta resolución y extrae el texto mediante **Tesseract OCR**.
- **Sin dependencia externa de Poppler:** Utiliza pypdfium2 para renderizar PDFs de manera nativa, ligera y sin necesidad de instalar binarios adicionales de Poppler.
- **Detección inteligente de códigos:**
  - Busca patrones como `Módulo: NM1A GE0558` y extrae el identificador del paciente (ej. `GE0558`).
  - Detecta identificadores alternativos como `Código paciente: [CÓDIGO]`.
  - Expresiones regulares con tolerancia a imperfecciones típicas de escaneo u OCR (con o sin tildes, mayúsculas/minúsculas).
- **Agrupación continua de historias clínicas:** Si una página interna no incluye encabezado con código, se asigna automáticamente al último paciente detectado.
- **Interfaz Gráfica amigable (GUI):** Selector de archivos y carpetas, barra de progreso en tiempo real y terminal de log integrada.
- **100% Local y Seguro:** El procesamiento se realiza completamente offline en tu máquina. Ningún dato médico es transmitido a la nube.

---

## ?? Requisitos previos

1. **Python 3.8 o superior** instalado.
2. **Tesseract OCR**:
   - Descargar el instalador para Windows desde [UB-Mannheim Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki).
   - Instalarlo en la ruta estándar (por ejemplo C:\Program Files\Tesseract-OCR). El programa detecta esta ubicación automáticamente.
   - *Opcional:* Si se desea reconocimiento en español, asegurarse de marcar el paquete de idioma español (*Spanish*) durante la instalación de Tesseract.

---

## ??? Instalación

1. **Clonar este repositorio:**
   `ash
   git clone https://github.com/TU-USUARIO/clinical-pdf-splitter.git
   cd clinical-pdf-splitter
   `

2. **(Recomendado) Crear y activar un entorno virtual:**
   `ash
   python -m venv venv
   # En Windows:
   venv\Scripts\activate
   `

3. **Instalar las dependencias:**
   `ash
   pip install -r requirements.txt
   `

---

## ?? Uso

1. Iniciar la aplicación:
   `ash
   python pdf_splitter.py
   `
2. En la ventana que aparece:
   - Presionar **"Seleccionar PDF..."** y elegir el archivo escaneado con las historias clínicas.
   - Seleccionar la **carpeta de salida** (por defecto sugerirá una carpeta llamada Pacientes_Separados).
   - Hacer clic en **"? Procesar"**.
3. El log detallará cada página procesada y los archivos resultantes generados (ej. GE0558.pdf).

---

## ?? Estructura del proyecto

`	ext
clinical-pdf-splitter/
¦
+-- pdf_splitter.py     # Aplicación principal (GUI, OCR y lógica de división)
+-- requirements.txt    # Dependencias de Python
+-- .gitignore          # Exclusión de archivos temporales y PDFs de datos
+-- README.md           # Documentación del proyecto
`

---

## ?? Privacidad de datos

Este software está diseñado para el ámbito de la salud:
- El archivo .gitignore incluye exclusiones para todos los archivos .pdf, garantizando que ninguna historia clínica real o dato sensible sea subido por accidente a los repositorios de control de versiones.
