# Laboratorio FyQ

**Control de stock y viabilidad de prácticas para el laboratorio de Física y Química de Secundaria.**

Aplicación local para el profesorado: guarda el inventario del laboratorio, lee los guiones de prácticas en PDF, calcula el material necesario para el grupo y avisa en grande de si la práctica **ES VIABLE** o **NO ES VIABLE** (y qué falta).

## Descargar e instalar

**[⬇ Página de descargas (Release v1.0)](https://github.com/javixxins/LABORATORIO-FYQ/releases/latest)**

| Sistema | Descarga directa | Instrucciones |
|---|---|---|
| **Windows 10/11** | [LaboratorioFyQ_Windows_v1.0.zip](https://github.com/javixxins/LABORATORIO-FYQ/releases/download/v1.0/LaboratorioFyQ_Windows_v1.0.zip) | Descomprimir y doble clic en «Instalar Laboratorio FyQ.bat». Python incluido. |
| **macOS 10.15+** | [LaboratorioFyQ_Mac_v1.0.dmg](https://github.com/javixxins/LABORATORIO-FYQ/releases/download/v1.0/LaboratorioFyQ_Mac_v1.0.dmg) | Abrir el DMG y arrastrar la app a Aplicaciones. |

Guía de uso completa con capturas: [Tutorial_Laboratorio_FyQ.pdf](https://github.com/javixxins/LABORATORIO-FYQ/releases/download/v1.0/Tutorial_Laboratorio_FyQ.pdf)

> Los instaladores no están firmados: la primera vez, en Mac usa clic derecho → «Abrir»; en Windows, «Más información» → «Ejecutar de todas formas».

## Funciones

- **Inventario por categorías** (Recipientes, Reactivos, Instrumentos, Otros y las que añadas): entradas de compras, descuentos, material **roto / no disponible**, stock mínimo e historial de movimientos.
- **Lectura de guiones en PDF**: detecta la lista de material y reactivos, cantidades y unidades, y la asigna al stock (aprende las asignaciones manuales).
- **Viabilidad**: escala el material al número de alumnos, aplica margen de seguridad en reactivos y comprueba mesas, sillas y capacidad del laboratorio. Si no es viable indica qué falta y para cuántos alumnos alcanza.
- **Reparto automático de alumnos**: individual, parejas, tríos o grupos de 4; con número impar forma parejas + un grupo de 3. Modo automático que elige el agrupamiento que cabe y tiene material.
- **Informe PDF** descargable con el reparto, el material por puesto y un **croquis del laboratorio** con los nombres de los alumnos.
- **Cursos y grupos** con listado de alumnos (pegar o importar .txt/.csv).
- **Proyectos `.labfyq`** para guardar y retomar prácticas; **exportar/importar el stock** entre ordenadores (archivo con fecha y hora).
- Logo y datos del instituto. Funciona sin Internet; los datos se quedan en el ordenador.

## Ejecutar desde el código

Requiere Python 3.9+ con `flask` y `pypdf`.

```bash
python3 launch.py
```

Abre el navegador en `http://127.0.0.1:8642` (si el puerto está ocupado usa el siguiente libre). Los datos se guardan en `datos/`.

Para regenerar los instalables:

```bash
python3 construccion/construir.py /ruta/python-3.12.10-embed-amd64.zip
```

## Estructura

```
server.py        servidor local (Flask + SQLite): stock, lectura de guiones, viabilidad, informes
pdfgen.py        generador de PDF sin dependencias
launch.py        lanzador (busca puerto libre y abre el navegador)
static/          interfaz web (HTML, CSS, JS)
construccion/    script que genera los instalables de Mac y Windows
Mac/, Windows/   instalables
ejemplos/        guion de práctica de ejemplo
```
