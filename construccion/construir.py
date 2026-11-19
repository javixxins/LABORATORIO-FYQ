# -*- coding: utf-8 -*-
"""Genera los instalables de Laboratorio FyQ para Mac y Windows.

    python3 construccion/construir.py /ruta/python-3.12.10-embed-amd64.zip

Resultado:
    Mac/LaboratorioFyQ_Mac_v<versión>.dmg
    Windows/LaboratorioFyQ_Windows_v<versión>.zip
"""
import os
import shutil
import subprocess
import sys
import zipfile

VERSION = "1.0"
NOMBRE = "Laboratorio FyQ"
PROY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(PROY, "construccion", "_tmp")
OUT_MAC = os.path.join(PROY, "Mac")
OUT_WIN = os.path.join(PROY, "Windows")

PAQUETES = ["flask", "werkzeug", "jinja2", "markupsafe", "itsdangerous", "click", "blinker", "pypdf",
            "importlib_metadata", "zipp", "typing_extensions"]
ARCHIVOS_APP = ["server.py", "pdfgen.py", "launch.py"]


def limpiar(d):
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)


def ignora(_dir, nombres):
    return [n for n in nombres if n == "__pycache__" or n.endswith((".pyc", ".so", ".pyd", ".dylib")) or n == ".DS_Store"]


def copiar_libs(destino):
    import importlib.metadata as md
    import importlib.util
    os.makedirs(destino, exist_ok=True)
    for p in PAQUETES:
        dist = md.distribution(p)
        spec = importlib.util.find_spec(p)
        origen = spec.origin
        if spec.submodule_search_locations:
            shutil.copytree(list(spec.submodule_search_locations)[0], os.path.join(destino, p), ignore=ignora)
        else:
            shutil.copy2(origen, destino)
        # metadatos (algunas librerías consultan su versión)
        info = str(dist._path)  # noqa
        if os.path.isdir(info):
            shutil.copytree(info, os.path.join(destino, os.path.basename(info)), ignore=ignora)
        print("  +", p, dist.version)


def app_base(destino):
    os.makedirs(destino, exist_ok=True)
    for f in ARCHIVOS_APP:
        shutil.copy2(os.path.join(PROY, f), destino)
    shutil.copytree(os.path.join(PROY, "static"), os.path.join(destino, "static"), ignore=ignora)
    ej = os.path.join(PROY, "ejemplos")
    if os.path.isdir(ej):
        shutil.copytree(ej, os.path.join(destino, "ejemplos"), ignore=ignora)
    copiar_libs(os.path.join(destino, "lib"))


def escribir(path, texto, crlf=False, bom=False):
    if crlf:
        texto = texto.replace("\r\n", "\n").replace("\n", "\r\n")
    with open(path, "wb") as f:
        if bom:
            f.write(b"\xef\xbb\xbf")
        f.write(texto.encode("utf-8"))


# ===================================================================== MAC
LANZADOR_MAC = r'''#!/bin/bash
# Laboratorio FyQ - lanzador
APP="$(cd "$(dirname "$0")/../Resources/app" && pwd)"
PY=""
for c in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  if [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  osascript -e 'display dialog "Laboratorio FyQ necesita Python 3, que viene con las «Herramientas de línea de comandos» de Apple.\n\nPulsa «Instalar» en la ventana que aparecerá (es gratuito y oficial de Apple) y, cuando termine, vuelve a abrir Laboratorio FyQ." buttons {"Aceptar"} default button 1 with title "Laboratorio FyQ" with icon caution' >/dev/null 2>&1
  xcode-select --install >/dev/null 2>&1
  exit 1
fi
exec "$PY" "$APP/launch.py" --instalado
'''

PLIST = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Laboratorio FyQ</string>
  <key>CFBundleDisplayName</key><string>Laboratorio FyQ</string>
  <key>CFBundleIdentifier</key><string>es.laboratorio.fyq</string>
  <key>CFBundleVersion</key><string>{v}</string>
  <key>CFBundleShortVersionString</key><string>{v}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>lanzar</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>10.15</string>
  <key>LSUIElement</key><true/>
  <key>NSHumanReadableCopyright</key><string>Departamento de Física y Química</string>
</dict></plist>
'''

LEEME_MAC = '''LABORATORIO FyQ {v} · INSTALACIÓN EN MAC
==========================================

1. Abre el archivo LaboratorioFyQ_Mac_v{v}.dmg (doble clic).
2. Arrastra «Laboratorio FyQ» a la carpeta «Aplicaciones».
3. Abre «Laboratorio FyQ» desde Aplicaciones (o desde Launchpad).
   La app se abre en tu navegador, en http://127.0.0.1:8642

LA PRIMERA VEZ
  · Como la app no se ha descargado del App Store, macOS puede decir que
    «no se puede abrir porque es de un desarrollador no identificado».
    Solución: en Aplicaciones, haz clic derecho (o Ctrl + clic) sobre
    «Laboratorio FyQ» → «Abrir» → «Abrir». Solo hay que hacerlo una vez.
    (En macOS 15: Ajustes del Sistema → Privacidad y seguridad → «Abrir igualmente».)
  · Si el Mac no tiene Python 3, la app te ofrecerá instalar las
    «Herramientas de línea de comandos» de Apple (gratis). Acepta, espera a
    que terminen y vuelve a abrir la app.

TUS DATOS
  Se guardan en: ~/Library/Application Support/Laboratorio FyQ
  Al actualizar o reinstalar la app no se pierden.
  Para pasar el inventario a otro ordenador: sección «Exportar / importar stock».

DESINSTALAR
  Arrastra «Laboratorio FyQ» de Aplicaciones a la Papelera.
  (Si quieres borrar también los datos, borra la carpeta indicada arriba.)

Requisitos: macOS 10.15 o posterior (Intel o Apple Silicon).
'''


def construir_mac():
    print("· Mac")
    limpiar(OUT_MAC)
    stage = os.path.join(TMP, "mac")
    limpiar(stage)
    app = os.path.join(stage, NOMBRE + ".app")
    res = os.path.join(app, "Contents", "Resources")
    os.makedirs(os.path.join(app, "Contents", "MacOS"))
    os.makedirs(res)
    escribir(os.path.join(app, "Contents", "Info.plist"), PLIST.format(v=VERSION))
    lz = os.path.join(app, "Contents", "MacOS", "lanzar")
    escribir(lz, LANZADOR_MAC)
    os.chmod(lz, 0o755)
    icns = os.path.join(PROY, NOMBRE + ".app", "Contents", "Resources", "AppIcon.icns")
    shutil.copy2(icns, os.path.join(res, "AppIcon.icns"))
    app_base(os.path.join(res, "app"))
    subprocess.run(["xattr", "-cr", app], check=False)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True)
    os.symlink("/Applications", os.path.join(stage, "Aplicaciones"))
    escribir(os.path.join(stage, "LEEME - Instalación Mac.txt"), LEEME_MAC.format(v=VERSION))
    tut = os.path.join(PROY, "Tutorial_Laboratorio_FyQ.pdf")
    if os.path.exists(tut):
        shutil.copy2(tut, stage)
    dmg = os.path.join(OUT_MAC, "LaboratorioFyQ_Mac_v%s.dmg" % VERSION)
    subprocess.run(["hdiutil", "create", "-volname", NOMBRE, "-srcfolder", stage, "-ov", "-format", "UDZO", dmg],
                   check=True, stdout=subprocess.DEVNULL)
    shutil.copy2(os.path.join(stage, "LEEME - Instalación Mac.txt"), OUT_MAC)
    print("  ->", dmg)


# ===================================================================== WINDOWS
INSTALAR_BAT = '''@echo off
title Instalar Laboratorio FyQ
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
echo.
pause
'''

INSTALAR_PS1 = r'''# Instalador de Laboratorio FyQ para Windows
$ErrorActionPreference = 'Stop'
$src  = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $env:LOCALAPPDATA 'Programs\Laboratorio FyQ'
Write-Host ''
Write-Host '  LABORATORIO FyQ {v} - Instalación' -ForegroundColor Cyan
Write-Host "  Carpeta del programa: $dest"
Write-Host ''
try {{
  # cierra la app si está abierta (actualización)
  Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object {{ $_.CommandLine -like '*Laboratorio FyQ*' }} |
    ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
  Start-Sleep -Milliseconds 500
  foreach ($d in 'app','python') {{ $p = Join-Path $dest $d; if (Test-Path $p) {{ Remove-Item -Recurse -Force $p }} }}
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  Copy-Item -Recurse -Force (Join-Path $src 'app'), (Join-Path $src 'python') $dest
  foreach ($f in 'icono.ico','desinstalar.ps1','Tutorial_Laboratorio_FyQ.pdf') {{
    $p = Join-Path $src $f; if (Test-Path $p) {{ Copy-Item -Force $p $dest }}
  }}
  Get-ChildItem -Recurse $dest | Unblock-File -ErrorAction SilentlyContinue

  $py     = Join-Path $dest 'python\pythonw.exe'
  $launch = Join-Path $dest 'app\launch.py'
  $ico    = Join-Path $dest 'icono.ico'
  $sh = New-Object -ComObject WScript.Shell
  $menu = [Environment]::GetFolderPath('Programs')
  foreach ($dir in @([Environment]::GetFolderPath('Desktop'), $menu)) {{
    $l = $sh.CreateShortcut((Join-Path $dir 'Laboratorio FyQ.lnk'))
    $l.TargetPath = $py
    $l.Arguments = '"' + $launch + '" --instalado'
    $l.WorkingDirectory = Join-Path $dest 'app'
    $l.IconLocation = $ico
    $l.Description = 'Control de stock y viabilidad de prácticas de laboratorio'
    $l.Save()
  }}
  $tut = Join-Path $dest 'Tutorial_Laboratorio_FyQ.pdf'
  if (Test-Path $tut) {{
    $l = $sh.CreateShortcut((Join-Path $menu 'Laboratorio FyQ - Guía de uso.lnk')); $l.TargetPath = $tut; $l.Save()
  }}

  # aparece en Configuración > Aplicaciones > Aplicaciones instaladas
  $k = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\LaboratorioFyQ'
  New-Item -Path $k -Force | Out-Null
  Set-ItemProperty -Path $k -Name DisplayName     -Value 'Laboratorio FyQ'
  Set-ItemProperty -Path $k -Name DisplayVersion  -Value '{v}'
  Set-ItemProperty -Path $k -Name Publisher       -Value 'Departamento de Física y Química'
  Set-ItemProperty -Path $k -Name DisplayIcon     -Value $ico
  Set-ItemProperty -Path $k -Name InstallLocation -Value $dest
  Set-ItemProperty -Path $k -Name UninstallString -Value ('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $dest 'desinstalar.ps1') + '"')
  Set-ItemProperty -Path $k -Name NoModify -Value 1 -Type DWord
  Set-ItemProperty -Path $k -Name NoRepair -Value 1 -Type DWord

  Write-Host '  Instalación completada.' -ForegroundColor Green
  Write-Host '  Tienes el icono «Laboratorio FyQ» en el Escritorio y en el menú Inicio.'
  Write-Host '  Abriendo la aplicación en el navegador...'
  Start-Process -FilePath $py -ArgumentList ('"' + $launch + '" --instalado') -WorkingDirectory (Join-Path $dest 'app')
}} catch {{
  Write-Host ''
  Write-Host ('  ERROR: ' + $_.Exception.Message) -ForegroundColor Red
}}
'''

DESINSTALAR_PS1 = r'''# Desinstalador de Laboratorio FyQ
$dest = Join-Path $env:LOCALAPPDATA 'Programs\Laboratorio FyQ'
$datos = Join-Path $env:APPDATA 'Laboratorio FyQ'
Add-Type -AssemblyName System.Windows.Forms
$r = [System.Windows.Forms.MessageBox]::Show('¿Desinstalar Laboratorio FyQ?', 'Laboratorio FyQ', 'YesNo', 'Question')
if ($r -ne 'Yes') { exit }
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like '*Laboratorio FyQ*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 500
foreach ($l in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Laboratorio FyQ.lnk'),
                 (Join-Path ([Environment]::GetFolderPath('Programs')) 'Laboratorio FyQ.lnk'),
                 (Join-Path ([Environment]::GetFolderPath('Programs')) 'Laboratorio FyQ - Guía de uso.lnk'))) {
  if (Test-Path $l) { Remove-Item -Force $l }
}
Remove-Item -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\LaboratorioFyQ' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $dest -ErrorAction SilentlyContinue
if (Test-Path $datos) {
  $r = [System.Windows.Forms.MessageBox]::Show("¿Borrar también tus datos (inventario, grupos y prácticas)?`n`nSi eliges «No» se conservan en:`n$datos", 'Laboratorio FyQ', 'YesNo', 'Warning')
  if ($r -eq 'Yes') { Remove-Item -Recurse -Force $datos -ErrorAction SilentlyContinue }
}
[System.Windows.Forms.MessageBox]::Show('Laboratorio FyQ se ha desinstalado.', 'Laboratorio FyQ') | Out-Null
'''

LEEME_WIN = '''LABORATORIO FyQ {v} · INSTALACIÓN EN WINDOWS
=============================================

1. Descomprime LaboratorioFyQ_Windows_v{v}.zip
   (clic derecho → «Extraer todo...»). No lo ejecutes desde dentro del zip.
2. Abre la carpeta extraída y haz doble clic en «Instalar Laboratorio FyQ.bat».
3. Se crea el icono «Laboratorio FyQ» en el Escritorio y en el menú Inicio,
   y la app se abre en el navegador (http://127.0.0.1:8642).

No hace falta instalar Python ni nada más: va incluido.
No necesita permisos de administrador (se instala solo para tu usuario).

LA PRIMERA VEZ
  · Windows puede mostrar «Windows protegió su PC» (SmartScreen) porque el
    instalador no está firmado. Pulsa «Más información» → «Ejecutar de todas formas».
  · Si el firewall de Windows pregunta por Python, puedes pulsar «Cancelar»:
    la app solo funciona dentro de tu ordenador y no necesita acceso a la red.

TUS DATOS
  Se guardan en: %APPDATA%\\Laboratorio FyQ
  Al actualizar o reinstalar (volver a ejecutar el instalador) no se pierden.
  Para pasar el inventario a otro ordenador: sección «Exportar / importar stock».

DESINSTALAR
  Configuración → Aplicaciones → Aplicaciones instaladas → «Laboratorio FyQ» → Desinstalar.

Requisitos: Windows 10 u 11 (64 bits).
'''


def construir_win(embed_zip):
    print("· Windows")
    limpiar(OUT_WIN)
    stage_root = os.path.join(TMP, "win")
    limpiar(stage_root)
    stage = os.path.join(stage_root, "LaboratorioFyQ")
    os.makedirs(stage)
    app_base(os.path.join(stage, "app"))
    pyd = os.path.join(stage, "python")
    with zipfile.ZipFile(embed_zip) as z:
        z.extractall(pyd)
    pth = [n for n in os.listdir(pyd) if n.endswith("._pth")][0]
    zipname = pth.replace("._pth", ".zip")
    escribir(os.path.join(pyd, pth), "%s\n.\n..\\app\n..\\app\\lib\n" % zipname, crlf=True)
    from PIL import Image
    Image.open(os.path.join(PROY, "static", "icono.png")).save(
        os.path.join(stage, "icono.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    escribir(os.path.join(stage, "Instalar Laboratorio FyQ.bat"), INSTALAR_BAT, crlf=True)
    escribir(os.path.join(stage, "instalar.ps1"), INSTALAR_PS1.format(v=VERSION), crlf=True, bom=True)
    escribir(os.path.join(stage, "desinstalar.ps1"), DESINSTALAR_PS1, crlf=True, bom=True)
    escribir(os.path.join(stage, "LEEME - Instalación Windows.txt"), LEEME_WIN.format(v=VERSION), crlf=True, bom=True)
    tut = os.path.join(PROY, "Tutorial_Laboratorio_FyQ.pdf")
    if os.path.exists(tut):
        shutil.copy2(tut, stage)
    out = os.path.join(OUT_WIN, "LaboratorioFyQ_Windows_v%s.zip" % VERSION)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for raiz, _dirs, files in os.walk(stage):
            for f in files:
                full = os.path.join(raiz, f)
                z.write(full, os.path.relpath(full, stage_root))
    shutil.copy2(os.path.join(stage, "LEEME - Instalación Windows.txt"), OUT_WIN)
    print("  ->", out)


if __name__ == "__main__":
    if len(sys.argv) < 2 or not os.path.exists(sys.argv[1]):
        print(__doc__)
        sys.exit(1)
    limpiar(TMP)
    construir_mac()
    construir_win(sys.argv[1])
    shutil.rmtree(TMP)
    print("Listo.")
