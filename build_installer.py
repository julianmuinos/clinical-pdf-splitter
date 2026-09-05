"""
Script de compilación y empaquetado del instalador.
Construye el ejecutable con PyInstaller, copia Tesseract OCR con el modelo en español
y compila el instalador de Windows con Inno Setup.
"""

import os
import shutil
import subprocess
import sys

# Asegurar codificación utf-8 o fallback seguro en Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(BASE_DIR, "dist")
BUILD_DIR = os.path.join(BASE_DIR, "build")
BUNDLE_DIR = os.path.join(BASE_DIR, "dist_bundle")
INSTALLER_OUTPUT_DIR = os.path.join(BASE_DIR, "dist_installer")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "icon.ico")
ISS_SCRIPT = os.path.join(BASE_DIR, "installer.iss")


def find_tesseract():
    candidates = [
        r"C:\Program Files\Tesseract-OCR",
        r"C:\Program Files (x86)\Tesseract-OCR",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR"),
    ]
    for c in candidates:
        if os.path.isfile(os.path.join(c, "tesseract.exe")):
            return c
    return None


def find_iscc():
    # Buscar en PATH
    which_iscc = shutil.which("iscc")
    if which_iscc:
        return which_iscc
    
    candidates = [
        os.path.expanduser(r"~\AppData\Local\Programs\Inno Setup 6\ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def clean_directories():
    print("\n[1/5] Limpiando directorios previos...")
    for folder in [DIST_DIR, BUILD_DIR, BUNDLE_DIR]:
        if os.path.exists(folder):
            print(f"  Eliminando {folder}...")
            shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(INSTALLER_OUTPUT_DIR, exist_ok=True)
    os.makedirs(BUNDLE_DIR, exist_ok=True)


def run_pyinstaller():
    print("\n[2/5] Compilando con PyInstaller (modo onedir + consola)...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--console",
        f"--icon={ICON_PATH}",
        "--name=pdf_splitter",
        f"--add-data={ICON_PATH};assets",
        os.path.join(BASE_DIR, "pdf_splitter.py"),
    ]
    print("  Ejecutando:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=BASE_DIR)
    if res.returncode != 0:
        raise RuntimeError(f"Fallo en PyInstaller con código {res.returncode}")


def prepare_bundle(tesseract_dir):
    print("\n[3/5] Preparando paquete completo en dist_bundle...")
    pyinstaller_dist = os.path.join(DIST_DIR, "pdf_splitter")
    
    # Copiar contenido de la compilación de PyInstaller
    for item in os.listdir(pyinstaller_dist):
        s = os.path.join(pyinstaller_dist, item)
        d = os.path.join(BUNDLE_DIR, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

    # Asegurar carpeta assets
    bundle_assets = os.path.join(BUNDLE_DIR, "assets")
    os.makedirs(bundle_assets, exist_ok=True)
    shutil.copy2(ICON_PATH, os.path.join(bundle_assets, "icon.ico"))

    # Copiar Tesseract OCR
    print(f"  Copiando Tesseract desde {tesseract_dir}...")
    bundle_tesseract = os.path.join(BUNDLE_DIR, "tesseract")
    os.makedirs(bundle_tesseract, exist_ok=True)
    
    # Copiar tesseract.exe
    shutil.copy2(os.path.join(tesseract_dir, "tesseract.exe"), os.path.join(bundle_tesseract, "tesseract.exe"))
    
    # Copiar todas las DLLs necesarias
    for item in os.listdir(tesseract_dir):
        if item.lower().endswith(".dll"):
            shutil.copy2(os.path.join(tesseract_dir, item), os.path.join(bundle_tesseract, item))
            
    # Copiar tessdata (spa.traineddata, osd.traineddata, eng.traineddata)
    src_tessdata = os.path.join(tesseract_dir, "tessdata")
    dst_tessdata = os.path.join(bundle_tesseract, "tessdata")
    os.makedirs(dst_tessdata, exist_ok=True)
    
    for model in ["spa.traineddata", "osd.traineddata", "eng.traineddata"]:
        src_model = os.path.join(src_tessdata, model)
        if os.path.isfile(src_model):
            print(f"    + Modelo OCR: {model}")
            shutil.copy2(src_model, os.path.join(dst_tessdata, model))


def compile_installer(iscc_path):
    print(f"\n[4/5] Compilando instalador con Inno Setup ({iscc_path})...")
    cmd = [iscc_path, ISS_SCRIPT]
    res = subprocess.run(cmd, cwd=BASE_DIR)
    if res.returncode != 0:
        raise RuntimeError(f"Fallo en ISCC con código {res.returncode}")


def main():
    print("=" * 60)
    print(" GENERADOR DEL INSTALADOR AUTÓNOMO")
    print(" Separador de Historias Clínicas PDF")
    print("=" * 60)

    # 1. Verificar dependencias
    tesseract_dir = find_tesseract()
    if not tesseract_dir:
        print("[ERROR] No se encontró la instalación de Tesseract OCR en el sistema.")
        sys.exit(1)
    print(f"✔ Tesseract detectado: {tesseract_dir}")

    iscc_path = find_iscc()
    if not iscc_path:
        print("[ERROR] No se encontró ISCC.exe de Inno Setup.")
        sys.exit(1)
    print(f"✔ Inno Setup detectado: {iscc_path}")

    # 2. Limpieza
    clean_directories()

    # 3. PyInstaller
    run_pyinstaller()

    # 4. Preparar bundle con Tesseract y assets
    prepare_bundle(tesseract_dir)

    # 5. Compilar con Inno Setup
    compile_installer(iscc_path)

    # Resumen final
    installer_exe = os.path.join(INSTALLER_OUTPUT_DIR, "Instalador_Separador_HC_Setup.exe")
    if os.path.isfile(installer_exe):
        size_mb = os.path.getsize(installer_exe) / (1024 * 1024)
        print("\n" + "=" * 60)
        print(" ¡INSTALADOR GENERADO EXITOSAMENTE!")
        print("=" * 60)
        print(f"Ubicación: {installer_exe}")
        print(f"Tamaño: {size_mb:.2f} MB")
        print("\nListo para transferir y ejecutar en cualquier PC.")
    else:
        print("\n[ADVERTENCIA] No se encontró el archivo generado en dist_installer.")


if __name__ == "__main__":
    main()
