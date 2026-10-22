"""A painted cell of an e-mail table is READABLE, whatever accent colour the tenant chose.

The tenant's accent colour (``EmailAppearance.accent_color``, any ``#RRGGBB`` the panel accepts) is
the FIRST colour of the discipline palette (:func:`record_colors`), so it becomes the background of
the first discipline's cells, and, since R-T18 (#187), of that row's Data cell too. The text of
every cell is the body's ink (``_INK``, near-black). With a dark accent the first discipline's name
and its dates were dark on dark: measured on ``8ee7cbd``, ``#1f3a5f`` (a navy, the renderer's own
``_NAVY`` hue) gives 1.38:1 and ``#123456`` gives 1.24:1, against 4.5:1 for WCAG AA body text.

The six default colours and the light accents in use are 9.4:1 or more, so nobody has seen it yet.
On the owner's tenant the accent is a light yellow, at 9.41:1.

What is held here:

* **The twin**: a dark accent paints the first discipline's cell and its Data cell with an ink of
  at least 4.5:1. It is red on ``8ee7cbd``.
* **The sweep**: over all 4096 ``#RGB`` accents, every painted cell has an ink of at least 4.5:1, or,
  when no ink reaches it, the better of the two inks.
* **The controls**:
  * a light accent, and no appearance at all, render byte for byte what they rendered on
    ``8ee7cbd`` (digests taken there);
  * a cell the body ink already reads on gets no ink of its own (every default colour);
  * a white cell never gets one;
  * the TEXT part does not move: the colour is HTML only.

The contrast is computed HERE, from the WCAG 2.x formula, and not imported from the module. A
mutated formula there cannot make this file agree with it.

Everything is invented: the class codes, the disciplines, the dates.
"""

from __future__ import annotations

import hashlib
import re

import pytest

import cogno_praxis.email_fields as ef
from cogno_praxis.email_fields import (
    DEFAULT_PALETTE,
    EmailAppearance,
    EmailContext,
    record_colors,
    records_html,
    render_email_forms,
)

MONTH = "2026-11"
RECS = [
    {"Turma": "QZ_07", "Data": "07/11/2026", "Disciplina": "Zoologia Aplicada"},
    {"Turma": "QZ_07", "Data": "19/11/2026", "Disciplina": "Cálculo Numérico"},
    {"Turma": "XA_01", "Data": "06/11/2026", "Disciplina": "Redes de Computadores"},
    {"Turma": "XA_01", "Data": "08/11/2026", "Disciplina": "Zoologia Aplicada"},
    {"Turma": "XA_01", "Data": "22/11/2026", "Disciplina": "Óptica Geométrica"},
]
#: WCAG 2.x AA, body text.
AA = 4.5
WHITE = "#ffffff"

#: ``records_html(RECS)`` on ``8ee7cbd`` (the base), per accent: sha256[:16] and length. A light
#: accent must render these bytes after the change. ``""`` is no appearance at all; ``#fde2c4`` is
#: an accent that IS the first default colour, so it renders the no-appearance bytes.
BASE_DIGESTS = {
    "": ("69418ccfd29d3375", 3926),
    "#f2c14e": ("f513094a0d47d4f4", 3926),
    "#cfe8ff": ("edab7cb09607d787", 3926),
    "#f6d55c": ("bb9cc71498acc3a0", 3926),
    "#fde2c4": ("69418ccfd29d3375", 3926),
}


def _luminance(hex6: str) -> float:
    channels = [int(hex6[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _html(accent: str) -> str:
    app = EmailAppearance(accent_color=accent) if accent else None
    return records_html(RECS, colors=record_colors([RECS], app), month=MONTH)


def _painted(doc: str) -> "list[tuple[str, str, str]]":
    """``(text, background, ink)`` of every cell with a background other than white. The ink is
    the cell's own ``color:`` or, without one, the body's (``_INK``)."""
    out = []
    for style, text in re.findall(r'<td style="([^"]*)">(.*?)</td>', doc, flags=re.S):
        bg = re.search(r"background:(#[0-9a-fA-F]{6})", style)
        if not bg or bg.group(1).lower() == WHITE:
            continue
        ink = re.search(r"(?:^|;)color:(#[0-9a-fA-F]{6})", style)
        out.append((text, bg.group(1).lower(), (ink.group(1) if ink else ef._INK).lower()))
    return out


def test_the_body_ink_is_the_one_this_file_assumes():
    """The control of the reading above: a cell with no ``color:`` inherits the body's, and the body
    declares ``_INK``. If the body changed its ink, every number here would be about another one."""
    assert f"color:{ef._INK}" in ef._BODY_STYLE


# ── the twin ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("accent", ["#1f3a5f", "#123456", "#000000", "#7a1f1f"])
def test_GEMEO_a_dark_accent_paints_cells_that_read(accent):
    painted = [p for p in _painted(_html(accent)) if p[1] == accent]
    # the first discipline (Zoologia Aplicada, in both class groups) has the accent: its 2 cells
    # and their 2 Data cells
    assert len(painted) == 4, painted
    for text, bg, ink in painted:
        assert _contrast(ink, bg) >= AA, (text, bg, ink, round(_contrast(ink, bg), 2))


def test_GEMEO_every_accent_of_the_sweep_paints_cells_that_read():
    bad = []
    for n in range(4096):
        r, g, b = (n >> 8) & 15, (n >> 4) & 15, n & 15
        accent = f"#{r:x}{r:x}{g:x}{g:x}{b:x}{b:x}"
        for text, bg, ink in _painted(_html(accent)):
            best = max(_contrast(ef._INK, bg), _contrast(WHITE, bg))
            if _contrast(ink, bg) < min(AA, best) - 1e-9:
                bad.append((accent, bg, ink))
    assert not bad, (len(bad), bad[:5])


# ── the controls ────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("accent", sorted(BASE_DIGESTS))
def test_CONTROLO_a_light_accent_renders_the_base_s_bytes(accent):
    doc = _html(accent)
    assert (hashlib.sha256(doc.encode()).hexdigest()[:16], len(doc)) == BASE_DIGESTS[accent]


def test_CONTROLO_the_digest_sees_one_byte():
    """The digests above are not a constant: one byte of another accent moves them."""
    assert hashlib.sha256(_html("#f2c14f").encode()).hexdigest()[:16] != BASE_DIGESTS["#f2c14e"][0]


@pytest.mark.parametrize("colour", DEFAULT_PALETTE + ("#f2c14e", "#cfe8ff"))
def test_CONTROLO_a_cell_the_body_ink_reads_gets_no_ink_of_its_own(colour):
    assert _contrast(ef._INK, colour) >= AA
    styles = re.findall(r'<td style="([^"]*)">', _html(colour))
    assert not [s for s in styles if re.search(r"(?:^|;)color:", s)]


def test_CONTROLO_a_white_cell_never_gets_an_ink():
    styles = re.findall(r'<td style="([^"]*)">', _html("#1f3a5f"))
    white = [s for s in styles if f"background:{WHITE}" in s]
    assert white and not [s for s in white if re.search(r"(?:^|;)color:", s)]


def test_CONTROLO_the_text_part_does_not_move():
    """The ink is HTML only: the text the proposal shows and the «sim» compares is the same with a
    dark accent and with a light one, and the HTML of the dark one really is painted."""
    body = "Olá, Prof. [nome]!\n\n[aulas]\n\nAtenciosamente,"
    texts, docs = set(), {}
    for accent in ("#1f3a5f", "#f2c14e"):
        ctx = EmailContext(recipient_name="Teobaldo", tenant_name="Escola Exemplo", month=MONTH,
                           custom_tags={"aulas": ""}, free_tag_values={"aulas": RECS})
        values = {"nome": "Teobaldo", "aulas": ef.records_text(RECS)}
        _subject, text, doc = render_email_forms(
            "Cronograma", body, values, ctx, appearance=EmailAppearance(accent_color=accent))
        texts.add(text)
        docs[accent] = doc
    assert len(texts) == 1
    assert "background:#1f3a5f" in docs["#1f3a5f"]          # the dark accent reached a cell
