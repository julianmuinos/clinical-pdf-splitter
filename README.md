# Clinical PDF Splitter

Herramienta de escritorio en Python con interfaz gráfica para dividir archivos PDF escaneados que contienen múltiples historias clínicas o estudios médicos, separándolos en documentos individuales por paciente mediante **OCR** (Reconocimiento Óptico de Caracteres).

---

## Características principales

- **Procesamiento de PDFs escaneados:** Renderiza páginas a alta resolución y extrae el texto mediante **Tesseract OCR**.
- **Sin dependencia externa de Poppler:** Utiliza pypdfium2 para renderizar PDFs de manera nativa, ligera y sin necesidad de instalar binarios adicionales de Poppler.
- **Detección inteligente de códigos:**
  - Busca patrones con estructura `Módulo: <prefijo> <código>` y extrae el identificador del paciente.
  - **Prefijos de módulo verificados:** `NM0`, `NM1`, `NM2`, `NM3`, `NM4`, `NM5`, `NM10`, `NM1A`, `NM5B`, `NM9A` y variantes alfanuméricas.
  - **Formatos de código de paciente soportados:**
    - Solo numéricos de 1 a 4 dígitos (ej. `79`, `102`, `1710`).
    - 1 letra + 3 a 4 dígitos (ej. `P050`, `D0004`, `F0001`).
    - 2 letras + 4 dígitos (ej. `GE1347`, `PR0019`).
    - 3 letras + 3 dígitos (ej. `GEP086`).
  - **Mecanismo de respaldo:** Si una hoja no presenta el encabezado de módulo, detecta identificadores alternativos como `Código paciente: [CÓDIGO]`.
  - Expresiones regulares tolerantes a fallos típicos de escaneo u OCR (con o sin tildes, mayúsculas/minúsculas).
- **Agrupación continua de historias clínicas:** Si una página interna no incluye encabezado con código, se asigna automáticamente al último paciente detectado.
- **Interfaz Gráfica amigable (GUI):** Selector de archivos y carpetas, barra de progreso en tiempo real y terminal de log integrada.
- **100% Local y Seguro:** El procesamiento se realiza completamente offline en tu máquina. Ningún dato médico es transmitido a la nube.

---

## Requisitos previos

1. **Python 3.8 o superior** instalado.
2. **Tesseract OCR**:
   - Descargar el instalador para Windows desde [UB-Mannheim Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki).
   - Instalarlo en la ruta estándar (por ejemplo C:\Program Files\Tesseract-OCR). El programa detecta esta ubicación automáticamente.
   - *Opcional:* Si se desea reconocimiento en español, asegurarse de marcar el paquete de idioma español (*Spanish*) durante la instalación de Tesseract.

---

## Instalación

1. **Clonar este repositorio:**
   `bash
   git clone https://github.com/TU-USUARIO/clinical-pdf-splitter.git
   cd clinical-pdf-splitter
   `

2. **(Recomendado) Crear y activar un entorno virtual:**
   `bash
   python -m venv venv
   # En Windows:
   venv\Scripts\activate
   `

3. **Instalar las dependencias:**
   `bash
   pip install -r requirements.txt
   `

---

## Uso

1. Iniciar la aplicación:
   `bash
   python pdf_splitter.py
   `
2. En la ventana que aparece:
   - Presionar **"Seleccionar PDF..."** y elegir el archivo escaneado con las historias clínicas.
   - Seleccionar la **carpeta de salida** (por defecto sugerirá una carpeta llamada Pacientes_Separados).
   - Hacer clic en **"⚙ Procesar"**.
3. El log detallará cada página procesada y los archivos resultantes generados (ej. `GE3418.pdf`, `P050.pdf`, `1710.pdf`, `102.pdf`, `79.pdf`).

---

## Generar Instalador Autónomo para Windows

El proyecto incluye una herramienta automatizada para compilar un instalador `.exe` independiente, ideal para instalar la aplicación en otra computadora sin requerir la instalación previa de Python ni de Tesseract OCR:

1. Asegurarse de tener instalado **Inno Setup 6** en el sistema.
2. Ejecutar el script de construcción:
   ```bash
   python build_installer.py
   ```
3. El instalador final se generará en la carpeta `dist_installer/`:
   - Archivo: `Instalador_Separador_HC_Setup.exe`
   - Características: instalación por usuario (sin requerir permisos de administrador), accesos directos en Escritorio y Menú Inicio, y Tesseract OCR con el modelo de español 100% embebido.

---

## Estructura del proyecto

```text
clinical-pdf-splitter/
│
├── assets/
│   └── icon.ico            # Ícono oficial de la aplicación
├── build_installer.py      # Script automatizado para compilar el instalador
├── installer.iss           # Script de configuración de Inno Setup
├── pdf_splitter.py         # Aplicación principal (GUI, OCR y lógica de división)
├── requirements.txt        # Dependencias de Python
├── .gitignore              # Exclusión de archivos de build, temporales y PDFs
└── README.md               # Documentación del proyecto
```

---

## Privacidad de datos

Este software está diseñado para el ámbito de la salud:
- El archivo `.gitignore` incluye exclusiones para todos los archivos `.pdf`, garantizando que ninguna historia clínica real o dato sensible sea subido por accidente a los repositorios de control de versiones.
