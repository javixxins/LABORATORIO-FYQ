# -*- coding: utf-8 -*-
"""Lanzador de Laboratorio FyQ (Mac y Windows).

Si la app ya está en marcha, abre el navegador. Si no, busca un puerto libre
(a partir del 8642, sin tocar los que usan otras aplicaciones), arranca el servidor
en segundo plano y abre el navegador.

  python launch.py              -> datos en la carpeta «datos» junto al programa
  python launch.py --instalado  -> datos en la carpeta del usuario
                                   Mac:     ~/Library/Application Support/Laboratorio FyQ
                                   Windows: %APPDATA%\\Laboratorio FyQ
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

BASE = os.path.dirname(os.path.abspath(__file__))
PORTS = list(range(8642, 8662))
WIN = sys.platform.startswith("win")


def carpeta_datos():
    if os.environ.get("LABFYQ_DATA"):
        return os.environ["LABFYQ_DATA"]
    if "--instalado" in sys.argv:
        if WIN:
            raiz = os.environ.get("APPDATA") or os.path.expanduser("~")
        elif sys.platform == "darwin":
            raiz = os.path.expanduser("~/Library/Application Support")
        else:
            raiz = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        return os.path.join(raiz, "Laboratorio FyQ")
    return os.path.join(BASE, "datos")


DATA = carpeta_datos()


def es_nuestra(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % port, timeout=0.6) as r:
            d = json.loads(r.read().decode())
            if d.get("app") != "laboratorio-fyq":
                return False
            # misma carpeta de datos (evita confundir la versión instalada con otra copia)
            return not d.get("datos") or os.path.normcase(os.path.abspath(d["datos"])) == os.path.normcase(os.path.abspath(DATA))
    except Exception:
        return False


def libre(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def python_sin_consola():
    exe = sys.executable
    if WIN:
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(w):
            return w
    return exe


def main():
    os.makedirs(DATA, exist_ok=True)
    port_file = os.path.join(DATA, "puerto.txt")
    preferido = None
    try:
        preferido = int(open(port_file).read().strip())
    except Exception:
        pass
    candidatos = ([preferido] if preferido in PORTS else []) + [p for p in PORTS if p != preferido]

    for p in candidatos:
        if es_nuestra(p):
            webbrowser.open("http://127.0.0.1:%d/" % p)
            return

    port = next((p for p in candidatos if libre(p)), None)
    if port is None:
        print("No hay ningún puerto libre entre %d y %d" % (PORTS[0], PORTS[-1]))
        sys.exit(1)
    with open(port_file, "w") as f:
        f.write(str(port))
    env = dict(os.environ, LABFYQ_DATA=DATA)
    log = open(os.path.join(DATA, "servidor.log"), "a")
    kw = {}
    if WIN:
        kw["creationflags"] = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen([python_sin_consola(), os.path.join(BASE, "server.py"), str(port)], cwd=BASE, env=env,
                     stdout=log, stderr=log, stdin=subprocess.DEVNULL, **kw)
    for _ in range(80):
        if es_nuestra(port):
            break
        time.sleep(0.25)
    webbrowser.open("http://127.0.0.1:%d/" % port)


if __name__ == "__main__":
    main()
