"""Regenerate the architecture figure in the README.

    python3 -m venv .venv && .venv/bin/pip install fonttools
    .venv/bin/python assets/architecture/generate.py

Writes architecture.svg and architecture-dark.svg beside this file. It is drawn
the way ql-backend's architecture figure is, and with the same font, cache and
colours: the type is outlined from Inter at generation time, so the figure
renders the same on GitHub and Docker Hub and carries no font dependency.

What it shows, left to right: the host, where the browser and Docker's health
check are; the one published port; and the container, where nginx routes each
path to the app, the guide or ql-backend, which listens on loopback only.
"""

import pathlib
import re
import urllib.request
from dataclasses import dataclass

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

HERE = pathlib.Path(__file__).resolve().parent
# Shared with ql-backend's assets/logo/generate.py, so the font downloads once.
CACHE = pathlib.Path.home() / ".cache" / "ql-logo"
INTER_URL = "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf"

WIDTH, HEIGHT = 1000, 452
TITLE = "ql-app container architecture"
DESCRIPTION = ("The browser reaches the container on port 8080, the only published port. Inside, "
               "nginx serves the app at / and the user's guide at /doc/, and passes /ws/ to "
               "ql-backend, which listens on 127.0.0.1:9111 and prices with QuantLib. Docker's "
               "health check asks /ws/healthz.")


@dataclass(frozen=True)
class Theme:
    """Mantine's palette, as the logo, the frontend and ql-backend's figure use it."""
    teal: str
    teal_soft: str
    handle: str
    handle_soft: str
    ink: str
    muted: str
    line: str
    panel: str
    card: str
    edge: str


LIGHT = Theme(teal="#0ca678", teal_soft="#e6fcf5", handle="#fd7e14", handle_soft="#fff4e6",
              ink="#1a1b1e", muted="#5c5f66", line="#dee2e6", panel="#f8f9fa",
              card="#ffffff", edge="#adb5bd")
DARK = Theme(teal="#20c997", teal_soft="#0b3b30", handle="#ff922b", handle_soft="#3d2410",
             ink="#f1f3f5", muted="#a6a7ab", line="#373a40", panel="#1f2023",
             card="#25262b", edge="#5c5f66")


# Each nginx route's row, at the height of the card it routes to: the guide's
# and ql-backend's centres, and the app's row just under nginx's header.
ROUTES = {"/": 210, "/doc/": 240, "/ws/": 348}


def inter(weight):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "Inter.ttf"
    if not path.exists():
        urllib.request.urlretrieve(INTER_URL, path)
    return instantiateVariableFont(TTFont(path), {"wght": weight, "opsz": 32})


def mark(teal, handle):
    """The logo's Q, in its 64-unit box."""
    return (f'<circle cx="29" cy="28" r="18" fill="none" stroke="{teal}" stroke-width="6.5"/>'
            f'<path d="M34.5 33.5 Q41 42 51.5 43.5" fill="none" stroke="{teal}" '
            f'stroke-width="6.5" stroke-linecap="round"/>'
            f'<circle cx="52.5" cy="43.5" r="6.5" fill="{handle}"/>')


def num(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


class Figure:
    """Type is set from glyphs defined once, in font units, and placed with
    <use>, which keeps each file a few tens of kilobytes."""

    def __init__(self, theme, regular, semibold):
        self.t, self.fonts = theme, {False: regular, True: semibold}
        self.parts, self.glyphs, self.colours = [], {}, set()

    # -- type -------------------------------------------------------------
    def glyph(self, bold, ch):
        font = self.fonts[bold]
        name = font.getBestCmap()[ord(ch)]
        if (bold, name) not in self.glyphs:
            key = ("b" if bold else "r") + str(len(self.glyphs))
            pen = SVGPathPen(font.getGlyphSet())
            font.getGlyphSet()[name].draw(pen)
            d = re.sub(r"-?\d+\.\d+", lambda m: num(float(m.group())), pen.getCommands())
            self.glyphs[(bold, name)] = (key, d)
        return self.glyphs[(bold, name)][0], font["hmtx"][name][0]

    def width_of(self, text, size, bold=False, tracking=0.0):
        scale = size / self.fonts[bold]["head"].unitsPerEm
        return sum(self.glyph(bold, ch)[1] for ch in text) * scale + tracking * max(len(text) - 1, 0)

    def text(self, text, x, y, size, colour, bold=False, anchor="start", tracking=0.0):
        scale = size / self.fonts[bold]["head"].unitsPerEm
        width = self.width_of(text, size, bold, tracking)
        x = {"start": x, "middle": x - width / 2, "end": x - width}[anchor]
        uses = []
        for ch in text:
            key, advance = self.glyph(bold, ch)
            if ch != " ":
                uses.append(f'<use href="#{key}" x="{num(x / scale)}"/>')
            x += advance * scale + tracking
        self.parts.append(f'<g fill="{colour}" transform="translate(0 {num(y)}) '
                          f'scale({scale:.6g} {-scale:.6g})">' + "".join(uses) + "</g>")

    def label(self, text, x, y):
        """A small-caps section label."""
        self.text(text.upper(), x, y, 10.5, self.t.muted, bold=True, tracking=1.1)

    # -- shapes -----------------------------------------------------------
    def box(self, x, y, w, h, fill, stroke, radius=10, width=1.0, dash=None):
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<rect x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}" '
                          f'rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"{extra}/>')

    def card(self, x, y, w, h, accent=None):
        self.box(x, y, w, h, self.t.card, self.t.line)
        if accent:
            # A bar along the top edge, clipped to the card's rounded corners.
            self.parts.append(f'<path d="M{x} {y + 10} a10 10 0 0 1 10 -10 h{w - 20} '
                              f'a10 10 0 0 1 10 10 v-6 h-{w} z" fill="{accent}"/>')

    def pill(self, text, x, y, fg, bg, anchor="end"):
        """A rounded tag; x is its right edge, or its left with anchor="start"."""
        w = self.width_of(text, 10.5, bold=True) + 16
        left = x - w if anchor == "end" else x
        self.box(left, y - 13, w, 19, bg, bg, radius=9.5)
        self.text(text, left + w / 2, y + 0.5, 10.5, fg, bold=True, anchor="middle")
        return w

    def line(self, d, colour, width=1.4, dash=None, start=False, end=False):
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        if start or end:
            self.colours.add(colour)
        ends = (f' marker-start="url(#{self.marker(colour)})"' if start else "") + \
               (f' marker-end="url(#{self.marker(colour)})"' if end else "")
        self.parts.append(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}" '
                          f'stroke-linecap="round" stroke-linejoin="round"{extra}{ends}/>')

    def marker(self, colour):
        return "arrow-" + colour.lstrip("#")

    # -- the figure -------------------------------------------------------
    def host(self):
        t = self.t
        self.label("Your machine", 24, 104)
        self.card(24, 116, 188, 76)
        self.text("Browser", 40, 145, 15, t.ink, bold=True)
        self.text("localhost:8080", 40, 167, 12, t.muted)
        self.text("the workbench and guide", 40, 183, 11, t.muted)

        self.box(24, 298, 188, 64, "none", t.edge, dash="4 4")
        self.text("Docker health check", 40, 324, 14, t.ink, bold=True)
        self.text("every 30 s", 40, 344, 12, t.muted)

        self.text("Publish on 127.0.0.1 only:", 24, 404, 12, t.muted)
        self.text("ql-backend has no authentication.", 24, 421, 12, t.muted)

    def container(self):
        t = self.t
        self.box(262, 36, 718, 400, t.panel, t.line, radius=14)
        self.parts.append(f'<g transform="translate(280 50) scale(0.42)">{mark(t.teal, t.handle)}</g>')
        self.text("markccchiang/ql-app", 314, 70, 16, t.ink, bold=True)
        self.text("one container  ·  debian:trixie-slim  ·  user ql, under tini", 490, 70, 12, t.muted)

        # nginx, with one row per route, each level with what it routes to.
        self.label("Reverse proxy", 284, 104)
        x, w = 284, 236
        self.card(x, 116, w, 278, accent=t.teal)
        self.text("nginx", x + 18, 146, 15, t.ink, bold=True)
        self.pill("port 8080", x + w - 16, 141, t.teal, t.teal_soft)
        self.parts.append(f'<line x1="{x + 18}" y1="162" x2="{x + w - 18}" y2="162" stroke="{t.line}"/>')
        self.label("Static files", x + 18, 188)
        self.label("Proxied", x + 18, 322)
        # What each route serves, in one column after the widest path.
        column = x + 18 + max(self.width_of(p, 10.5, bold=True) + 16 for p in ROUTES) + 10
        for path, what in (("/", "the app"), ("/doc/", "the guide"), ("/ws/", "to ql-backend")):
            y = ROUTES[path]
            fg, bg = (t.handle, t.handle_soft) if path == "/ws/" else (t.teal, t.teal_soft)
            self.pill(path, x + 18, y + 4, fg, bg, anchor="start")
            self.text(what, column, y + 4.5, 12.5, t.ink)
        self.text("and /ws/healthz", x + 18, 378, 11, t.muted)

    def targets(self):
        t = self.t
        x, w = 616, 342
        self.label("Services", x, 104)

        self.card(x, 116, w, 76)
        self.text("Workbench app", x + 18, 145, 15, t.ink, bold=True)
        self.text("React + Mantine", x + w - 16, 145, 12, t.muted, anchor="end")
        self.text("ql-frontend, built by Vite", x + 18, 170, 12, t.muted)

        self.card(x, 202, w, 76)
        self.text("User's guide", x + 18, 231, 15, t.ink, bold=True)
        self.text("Sphinx", x + w - 16, 231, 12, t.muted, anchor="end")
        self.text("English and Traditional Chinese", x + 18, 256, 12, t.muted)

        # ql-backend sits behind a dashed loopback boundary: nothing outside
        # the container can reach it except through nginx.
        self.box(x - 8, 292, w + 16, 128, "none", t.edge, radius=12, dash="4 4")
        self.text("loopback only", x + w, 410, 11, t.muted, anchor="end")
        self.card(x, 302, w, 92, accent=t.handle)
        self.text("ql-backend", x + 18, 332, 15, t.ink, bold=True)
        self.pill("127.0.0.1:9111", x + w - 16, 327, t.handle, t.handle_soft)
        self.text("Live QuantLib sessions over Protobuf", x + 18, 356, 12, t.ink)
        self.text("QuantLib 1.43  ·  Protobuf 34  ·  one static binary", x + 18, 378, 12, t.muted)

    def wires(self):
        t = self.t
        # The one published port, HTTP and the WebSocket both ways; nginx's
        # "port 8080" pill names it.
        self.line("M214 154 C240 154 250 146 282 146", t.teal, width=1.8, start=True, end=True)
        # The health check comes in through the same door, to /ws/healthz.
        self.line("M214 330 C244 330 250 374 282 374", t.edge, dash="4 4", end=True)
        # nginx to what it serves. The socket is the live path, drawn in the
        # handle's orange as in the logo and ql-backend's figure.
        y = ROUTES["/"]
        self.line(f"M522 {y} C568 {y} 572 154 614 154", t.edge, end=True)
        self.line(f"M522 {ROUTES['/doc/']} H614", t.edge, end=True)
        self.line(f"M522 {ROUTES['/ws/']} H614", t.handle, width=2.2, start=True, end=True)
        self.text("WebSocket", 568, ROUTES["/ws/"] - 10, 11, t.handle, bold=True, anchor="middle")

    def render(self):
        self.host()
        self.container()
        self.targets()
        self.wires()
        glyphs = "".join(f'<path id="{key}" d="{d}"/>' for key, d in self.glyphs.values())
        markers = "".join(
            f'<marker id="{self.marker(c)}" viewBox="0 0 10 10" refX="8.5" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M1 1.5 L8.5 5 L1 8.5" fill="none" stroke="{c}" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round"/></marker>'
            for c in sorted(self.colours))
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
                f'width="{WIDTH}" height="{HEIGHT}" role="img" aria-labelledby="t d">'
                f'<title id="t">{TITLE}</title><desc id="d">{DESCRIPTION}</desc>'
                f'<defs>{markers}{glyphs}</defs>{"".join(self.parts)}</svg>\n')


def main():
    regular, semibold = inter(430), inter(650)
    for name, theme in (("architecture.svg", LIGHT), ("architecture-dark.svg", DARK)):
        (HERE / name).write_text(Figure(theme, regular, semibold).render(), encoding="utf-8")
        print("wrote", HERE / name)


if __name__ == "__main__":
    main()
