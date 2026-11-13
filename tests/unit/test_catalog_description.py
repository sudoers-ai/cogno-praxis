"""A catalog item's DESCRIPTION, as list_services prints it: a SECOND indented line after the item,
outside the name—duration—value—who grid, whitespace collapsed and clipped. An item with no
description renders the line byte-for-byte as before. The text is the business's own (third-party);
it reaches the model only inside the core's tool-result fence (the EGO twin lives host-side).
"""

from __future__ import annotations

from cogno_praxis.scheduler.catalog import (
    CatalogItem, DESCRIPTION_PRINT_CEILING, clip_description, format_product_line,
    format_service_line, render_service_catalog)
from cogno_praxis.scheduler.store import Host


def _service(description: str = "") -> CatalogItem:
    return CatalogItem(item_id="service:coloracao", kind="service", name="Coloração",
                       description=description, value_text="R$ 260,00", duration_minutes=120,
                       all_hosts=True)


def _product(description: str = "") -> CatalogItem:
    return CatalogItem(item_id="product:shampoo", kind="product", name="Shampoo",
                       description=description, value_text="R$ 60,00")


def test_no_description_renders_the_line_byte_for_byte_as_before():
    assert format_service_line(_service(), []) == "Coloração — 2 h — R$ 260,00 — todos"
    assert format_product_line(_product()) == "Shampoo — R$ 60,00"


def test_a_description_follows_on_a_second_indented_line_outside_the_grid():
    line = format_service_line(_service("Mechas, tonalização e finalização."), [])
    assert line == "Coloração — 2 h — R$ 260,00 — todos\n  descrição: Mechas, tonalização e finalização."
    # the GRID (first line) is untouched — the voice and nets read it
    assert line.splitlines()[0] == "Coloração — 2 h — R$ 260,00 — todos"
    assert format_product_line(_product("Repara pontas duplas.")) == \
        "Shampoo — R$ 60,00\n  descrição: Repara pontas duplas."


def test_line_breaks_collapse_so_the_description_never_fabricates_an_item_line():
    desc = "linha um\n- linha dois parece item\n\nlinha três"
    line = format_service_line(_service(desc), [])
    body = line.splitlines()
    # exactly two lines: the grid, and ONE indented description line (no bare «- » item line)
    assert len(body) == 2
    assert body[1] == "  descrição: linha um - linha dois parece item linha três"
    assert not any(l.lstrip().startswith("- ") for l in body[1:])


def test_a_description_over_the_ceiling_is_cut_at_a_word_boundary_with_an_ellipsis():
    long = "palavra " * 60                      # ~480 chars, well over the ceiling
    clipped = clip_description(long)
    assert clipped.endswith("…")
    assert len(clipped) <= DESCRIPTION_PRINT_CEILING + 1
    assert "palavra" in clipped and not clipped.endswith(" …")   # cut on a word boundary


def test_a_legible_description_arrives_whole_so_the_voice_can_use_it():
    desc = "Coloração completa com produtos veganos; inclui lavagem e escova."
    assert clip_description(desc) == desc           # under the ceiling → untouched
    assert desc in format_service_line(_service(desc), [])


def test_render_service_catalog_keeps_the_description_indented_under_its_item():
    out = render_service_catalog(
        [_service("Mechas e tonalização."), _product("Repara pontas.")],
        [Host("belmira", "Belmira", "Cabeleireira")])
    # the id is appended to the GRID line (in brackets); the description stays on the second line
    assert "- Coloração — 2 h — R$ 260,00 — todos [service:coloracao]\n  descrição: Mechas e tonalização." in out
    assert "- Shampoo — R$ 60,00 [product:shampoo]\n  descrição: Repara pontas." in out
