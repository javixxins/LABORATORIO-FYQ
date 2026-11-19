# -*- coding: utf-8 -*-
"""Generador de PDF mínimo, sin dependencias externas (Helvetica, WinAnsi).
Soporta texto, rectángulos, líneas, imágenes JPEG y saltos de página automáticos."""
import io
import re
import zlib

# anchos aproximados de Helvetica (1/1000 em) para caracteres ASCII imprimibles
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
      556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
      1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
      667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
      333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
      556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]

_REPL = {"–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...", "→": "->",
         "≥": ">=", "≤": "<=", "≈": "aprox.", "✔": "", "✖": "", "•": "-", "€": "EUR", "×": "x"}


_SYM = re.compile("[\u2600-\u27bf\u2190-\u21ff\u2b00-\u2bff\U0001F300-\U0001FAFF]\ufe0f?\\s?")


def _enc(s):
    s = str(s).replace("\uff0b", "+").replace("\uff0d", "-").replace("\u2192", "->")
    s = _SYM.sub("", s)
    s = "".join(_REPL.get(c, c) for c in s)
    return s.encode("cp1252", "replace")


def _width_char(c, bold):
    o = ord(c)
    w = _W[o - 32] if 32 <= o < 127 else 556
    if c in "ÁÉÍÓÚÑÜáéíóúñüºª¿¡":
        w = {"Á": 667, "É": 667, "Í": 278, "Ó": 778, "Ú": 722, "Ñ": 722, "Ü": 722}.get(c, 556 if c.islower() else 333)
        if c in "íÍ":
            w = 278
    return w * (1.06 if bold else 1.0)


def text_width(s, size, bold=False):
    return sum(_width_char(c, bold) for c in str(s)) * size / 1000.0


def _esc(b):
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def hex2rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class PDF:
    W, H = 595.28, 841.89  # A4 vertical en puntos
    M = 42

    def __init__(self, title=""):
        self.pages = []
        self.images = []
        self.title = title
        self.footer = ""
        self.new_page()

    # --------------------------------------------------------------- páginas
    def new_page(self, landscape=False):
        self.W, self.H = (841.89, 595.28) if landscape else (595.28, 841.89)
        self.ops = []
        self.page_imgs = set()
        self.pages.append((self.ops, self.page_imgs, self.W, self.H))
        self.y = self.H - self.M

    def ensure(self, h):
        if self.y - h < self.M + 20:
            self.new_page()
            return True
        return False

    # --------------------------------------------------------------- primitivas (y = desde arriba)
    def rect(self, x, y_top, w, h, fill=None, stroke=None, lw=0.6):
        y = y_top - h
        o = self.ops
        if fill:
            o.append("%.3f %.3f %.3f rg" % hex2rgb(fill))
        if stroke:
            o.append("%.3f %.3f %.3f RG %.2f w" % (hex2rgb(stroke) + (lw,)))
        op = "B" if fill and stroke else ("f" if fill else "S")
        o.append("%.2f %.2f %.2f %.2f re %s" % (x, y, w, h, op))

    def line(self, x1, y1, x2, y2, color="#cbd5e1", lw=0.6):
        self.ops.append("%.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S" % (hex2rgb(color) + (lw, x1, y1, x2, y2)))

    def text(self, x, y_base, s, size=10, bold=False, color="#0f172a", align="left", w=None):
        if align != "left" and w is not None:
            tw = text_width(s, size, bold)
            x = x + (w - tw) if align == "right" else x + (w - tw) / 2
        font = "F2" if bold else "F1"
        self.ops.append("BT %.3f %.3f %.3f rg /%s %.2f Tf %.2f %.2f Td (" % (hex2rgb(color) + (font, size, x, y_base))
                        + _esc(_enc(s)).decode("latin-1") + ") Tj ET")

    def wrap(self, s, size, width, bold=False):
        out = []
        for para in str(s).split("\n"):
            words = para.split(" ")
            line = ""
            for wd in words:
                cand = (line + " " + wd).strip()
                if text_width(cand, size, bold) <= width or not line:
                    line = cand
                else:
                    out.append(line)
                    line = wd
            out.append(line)
        return out

    def paragraph(self, s, size=10, bold=False, color="#0f172a", x=None, width=None, lead=1.35):
        x = self.M if x is None else x
        width = (self.W - 2 * self.M) if width is None else width
        for ln in self.wrap(s, size, width, bold):
            self.ensure(size * lead)
            self.y -= size * lead
            self.text(x, self.y + size * 0.25, ln, size, bold, color)

    def image_jpeg(self, data, px_w, px_h, x, y_top, w, h, gray=False):
        name = "Im%d" % (len(self.images) + 1)
        self.images.append((name, data, px_w, px_h, gray))
        self.page_imgs.add(name)
        self.ops.append("q %.2f 0 0 %.2f %.2f %.2f cm /%s Do Q" % (w, h, x, y_top - h, name))

    # --------------------------------------------------------------- tabla
    def table(self, cols, rows, widths, header_bg="#0f2a44", zebra="#f1f5f9", size=8.8, row_colors=None, aligns=None):
        """cols: títulos; rows: listas de celdas (str); widths: anchos en pt."""
        x0 = self.M
        aligns = aligns or ["left"] * len(cols)
        pad = 4

        def draw_header():
            h = size + 9
            self.ensure(h + 14)
            self.rect(x0, self.y, sum(widths), h, fill=header_bg)
            x = x0
            for c, w, a in zip(cols, widths, aligns):
                self.text(x + pad, self.y - h + 5.5, c, size, True, "#ffffff", a, w - 2 * pad)
                x += w
            self.y -= h

        draw_header()
        for i, r in enumerate(rows):
            cells = [self.wrap(c, size, w - 2 * pad) for c, w in zip(r, widths)]
            nlines = max(len(c) for c in cells)
            h = nlines * size * 1.25 + 7
            if self.ensure(h):
                draw_header()
            bg = (row_colors[i] if row_colors and row_colors[i] else (zebra if i % 2 else None))
            if bg:
                self.rect(x0, self.y, sum(widths), h, fill=bg)
            x = x0
            for lines, w, a in zip(cells, widths, aligns):
                yy = self.y - size - 2.5
                for ln in lines:
                    self.text(x + pad, yy, ln, size, False, "#0f172a", a, w - 2 * pad)
                    yy -= size * 1.25
                x += w
            self.line(x0, self.y - h, x0 + sum(widths), self.y - h, "#e2e8f0", 0.4)
            self.y -= h

    # --------------------------------------------------------------- salida
    def output(self):
        objs = []

        def add(b):
            objs.append(b if isinstance(b, bytes) else b.encode("latin-1"))
            return len(objs)

        f1 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        img_ids = {}
        for name, data, pw, ph, gray in self.images:
            cs = "/DeviceGray" if gray else "/DeviceRGB"
            hdr = ("<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s /BitsPerComponent 8 "
                   "/Filter /DCTDecode /Length %d >>\nstream\n" % (pw, ph, cs, len(data))).encode("latin-1")
            img_ids[name] = add(hdr + data + b"\nendstream")
        pages_id_placeholder = len(objs) + 1
        add("")  # se rellena después (Pages)
        page_ids = []
        total = len(self.pages)
        for n, (ops, imgs, pw_, ph_) in enumerate(self.pages, 1):
            ops = list(ops)
            if self.footer:
                ops.append("BT 0.39 0.45 0.55 rg /F1 7.5 Tf %.2f 22 Td (%s) Tj ET"
                           % (self.M, _esc(_enc(self.footer)).decode("latin-1")))
            pn = "Página %d de %d" % (n, total)
            ops.append("BT 0.39 0.45 0.55 rg /F1 7.5 Tf %.2f 22 Td (%s) Tj ET"
                       % (pw_ - self.M - text_width(pn, 7.5), _esc(_enc(pn)).decode("latin-1")))
            content = zlib.compress("\n".join(ops).encode("latin-1"))
            cid = add(("<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(content)).encode("latin-1")
                      + content + b"\nendstream")
            xo = " ".join("/%s %d 0 R" % (nm, img_ids[nm]) for nm in sorted(imgs))
            res = "<< /Font << /F1 %d 0 R /F2 %d 0 R >>%s >>" % (f1, f2, (" /XObject << %s >>" % xo) if xo else "")
            page_ids.append(add("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Resources %s /Contents %d 0 R >>"
                                % (pages_id_placeholder, pw_, ph_, res, cid)))
        objs[pages_id_placeholder - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>"
                                          % (" ".join("%d 0 R" % p for p in page_ids), len(page_ids))).encode("latin-1")
        info = add(b"<< /Title (" + _esc(_enc(self.title)) + b") /Producer (Laboratorio FyQ) >>")
        cat = add("<< /Type /Catalog /Pages %d 0 R >>" % pages_id_placeholder)

        buf = io.BytesIO()
        buf.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offs = []
        for i, o in enumerate(objs, 1):
            offs.append(buf.tell())
            buf.write(("%d 0 obj\n" % i).encode("latin-1") + o + b"\nendobj\n")
        xref = buf.tell()
        buf.write(("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode("latin-1"))
        for off in offs:
            buf.write(("%010d 00000 n \n" % off).encode("latin-1"))
        buf.write(("trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                   % (len(objs) + 1, cat, info, xref)).encode("latin-1"))
        return buf.getvalue()
