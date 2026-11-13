"""The services+products catalog: the shared validator, both doors, and the reads.

Real-form twins for the owner's rules of 12/11: ``kind`` is explicit (a service without a
duration is INVALID, never a product); a service needs a duration (a positive multiple of 30) and
someone to perform it; a product forbids both; two namesakes are told apart by the roster label,
and two with the same label go to the screen; the total is summed in code and refuses an item with
no value or two currencies; a GUEST never sees the team report. The professional names are rare
inventions so no real person's name reads as a label.
"""

from __future__ import annotations

import logging

import pytest

from cogno_praxis.scheduler import catalog as C
from cogno_praxis.scheduler.store import Host


def _salon() -> "list[Host]":
    return [Host("belmira", "Belmira Quostral", "Cabeleireira"),
            Host("thessaly", "Thessaly Vendrim", "Manicure")]


# ── the import door: sections, per-type validation ──────────────────────────────────────────
def test_sections_parse_services_and_products():
    hosts = _salon()
    block = ("SERVIÇOS (nome | duração | valor | profissionais):\n"
             "- Coloração | 120 min | R$ 260,00 | Belmira, Thessaly\n"
             "- Manicure | 30 min | R$ 45,00 | todos\n"
             "PRODUTOS (nome | valor):\n"
             "- Shampoo reparador | R$ 60,00\n")
    parse = C.parse_catalog_block(block, hosts)
    assert not parse.invalid
    assert [i.item_id for i in parse.services] == ["service:coloracao", "service:manicure"]
    assert parse.services[0].host_ids == ("belmira", "thessaly")
    assert parse.services[1].all_hosts is True and parse.services[1].host_ids == ()
    assert [i.item_id for i in parse.products] == ["product:shampoo_reparador"]


def test_a_bullet_before_any_section_is_out_of_section():
    parse = C.parse_catalog_block("- Coloração | 120 min | R$ 260,00 | Belmira\n", _salon())
    assert [i.reason for i in parse.invalid] == [C.REASON_OUT_OF_SECTION]
    assert not parse.items


def test_service_without_duration_is_invalid_not_a_product():
    """``kind`` is explicit: a missing duration does NOT demote a service to a product."""
    block = "SERVIÇOS:\n- Corte | | R$ 40,00 | Belmira\n"
    parse = C.parse_catalog_block(block, _salon())
    assert not parse.items
    assert [i.reason for i in parse.invalid] == [C.REASON_SERVICE_NO_DURATION]


def test_duration_must_be_a_multiple_of_thirty():
    parse = C.parse_catalog_block("SERVIÇOS:\n- Escova | 20 min | R$ 50,00 | Belmira\n", _salon())
    assert [i.reason for i in parse.invalid] == [C.REASON_DURATION_NOT_MULTIPLE]


def test_a_product_may_not_carry_a_duration_or_a_professional():
    hosts = _salon()
    s = C.validate_item_dicts(
        [{"kind": "product", "name": "Pomada", "value_text": "R$ 30,00", "duration_minutes": 30}],
        hosts)
    assert [i.reason for i in s.invalid] == [C.REASON_PRODUCT_WITH_DURATION]
    s2 = C.validate_item_dicts(
        [{"kind": "product", "name": "Pomada", "value_text": "R$ 30,00", "host_ids": ["belmira"]}],
        hosts)
    assert [i.reason for i in s2.invalid] == [C.REASON_PRODUCT_WITH_PROFESSIONAL]


def test_a_service_needs_someone_to_perform_it():
    s = C.validate_item_dicts(
        [{"kind": "service", "name": "Hidratação", "value_text": "R$ 80,00",
          "duration_minutes": 60, "host_ids": []}], _salon())
    assert [i.reason for i in s.invalid] == [C.REASON_NO_PROFESSIONAL]


def test_value_is_optional_but_unreadable_when_present_is_invalid():
    hosts = _salon()
    ok = C.parse_catalog_block("PRODUTOS:\n- Toalha |\n", hosts)
    assert ok.products and ok.products[0].value_text == ""
    bad = C.parse_catalog_block("PRODUTOS:\n- Toalha | grátis mesmo\n", hosts)
    assert [i.reason for i in bad.invalid] == [C.REASON_VALUE]


# ── the name-checker: not found / homonyms, told apart by the roster label ───────────────────
def test_a_name_that_matches_nobody_is_reported_with_the_roster_to_the_team_only():
    hosts = _salon()
    block = "SERVIÇOS:\n- Massagem | 60 min | R$ 90,00 | Belmyra\n"   # typo
    parse = C.parse_catalog_block(block, hosts)
    assert [i.reason for i in parse.invalid] == [C.REASON_PROFESSIONAL_NOT_FOUND]
    team = C.render_catalog_report(parse, hosts, "EMPLOYEE")
    assert "profissional não encontrado: Belmyra" in team
    assert "Belmira Quostral (Cabeleireira)" in team       # the roster, with labels
    assert C.render_catalog_report(parse, hosts, "GUEST") == ""   # the GUEST sees nothing


def test_two_namesakes_are_refused_with_the_labels_to_write():
    hosts = [Host("odal1", "Odalric Penumbra", "Cabeleireiro"),
             Host("odal2", "Odalric Penumbra", "Manicure")]
    block = "SERVIÇOS:\n- Corte | 30 min | R$ 40,00 | Odalric Penumbra\n"
    parse = C.parse_catalog_block(block, hosts)
    assert [i.reason for i in parse.invalid] == [C.REASON_HOMONYM]
    assert set(parse.invalid[0].labels) == {"Odalric Penumbra (Cabeleireiro)",
                                            "Odalric Penumbra (Manicure)"}
    # the exact label resolves to that one professional (the P-1 guarantee)
    ok = C.parse_catalog_block(
        "SERVIÇOS:\n- Corte | 30 min | R$ 40,00 | Odalric Penumbra (Manicure)\n", hosts)
    assert ok.services and ok.services[0].host_ids == ("odal2",)


def test_two_with_the_same_label_go_to_the_screen():
    hosts = [Host("m1", "Marnix Threlkeld", "Manicure"),
             Host("m2", "Marnix Threlkeld", "Manicure")]
    parse = C.parse_catalog_block(
        "SERVIÇOS:\n- Unha | 30 min | R$ 35,00 | Marnix Threlkeld\n", hosts)
    assert [i.reason for i in parse.invalid] == [C.REASON_HOMONYMS_INDISTINCT]


# ── duplicates, stability, the shared validator ─────────────────────────────────────────────
def test_a_duplicate_name_invalidates_every_line_that_shares_it():
    block = ("SERVIÇOS:\n- Corte | 30 min | R$ 40,00 | Belmira\n"
             "- Corte | 60 min | R$ 80,00 | Thessaly\n")
    parse = C.parse_catalog_block(block, _salon())
    assert not parse.items
    assert [i.reason for i in parse.invalid] == [C.REASON_DUPLICATE, C.REASON_DUPLICATE]


def test_a_reimport_of_the_same_block_keeps_the_ids():
    block = "SERVIÇOS:\n- Coloração | 120 min | R$ 260,00 | Belmira\n"
    a = C.parse_catalog_block(block, _salon())
    b = C.parse_catalog_block(block, _salon())
    assert [i.item_id for i in a.items] == [i.item_id for i in b.items] == ["service:coloracao"]


def test_both_doors_run_the_same_validator():
    """The screen door (ids) and the paste door (names) reach the same item and the same reason."""
    hosts = _salon()
    screen = C.validate_item_dicts(
        [{"kind": "service", "name": "Coloração", "value_text": "R$ 260,00",
          "duration_minutes": 120, "host_ids": ["belmira"]}], hosts)
    paste = C.parse_catalog_block(
        "SERVIÇOS:\n- Coloração | 120 min | R$ 260,00 | Belmira\n", hosts)
    assert screen.items[0].item_id == paste.items[0].item_id == "service:coloracao"
    assert screen.items[0].host_ids == paste.items[0].host_ids == ("belmira",)
    # an unknown id (screen) and an unknown name (paste) both reject the line
    bad_screen = C.validate_item_dicts(
        [{"kind": "service", "name": "X", "duration_minutes": 30, "host_ids": ["ghost"]}], hosts)
    assert [i.reason for i in bad_screen.invalid] == [C.REASON_PROFESSIONAL_NOT_FOUND]


# ── reading: two lists, description, rename / lost schedule ───────────────────────────────
def test_render_gives_two_lists_with_current_names_and_descriptions():
    hosts = _salon()
    items = C.validate_item_dicts([
        {"kind": "service", "name": "Coloração", "value_text": "R$ 260,00",
         "duration_minutes": 120, "host_ids": ["belmira"], "description": "coloração completa"},
        {"kind": "product", "name": "Shampoo", "value_text": "R$ 60,00"}], hosts).items
    out = C.render_service_catalog(items, hosts)
    assert "Serviços:" in out and "Produtos:" in out
    assert "Coloração — 2 h — R$ 260,00 — Belmira Quostral" in out
    # a rename in the directory shows the NEW name (the link is the host_id)
    renamed = [Host("belmira", "Belmira Quostral-Nova", "Cabeleireira"), hosts[1]]
    assert "Belmira Quostral-Nova" in C.render_service_catalog(items, renamed)


def test_a_service_whose_only_professional_lost_the_schedule_is_unoffered(caplog):
    hosts = _salon()
    items = C.validate_item_dicts(
        [{"kind": "service", "name": "Coloração", "value_text": "R$ 260,00",
          "duration_minutes": 120, "host_ids": ["belmira"]}], hosts).items
    gone: "list[Host]" = [hosts[1]]          # belmira no longer has a schedule
    assert C.unoffered_count(items, gone) == 1
    with caplog.at_level(logging.DEBUG, logger="cogno_praxis.scheduler.catalog"):
        out = C.render_service_catalog(items, gone)
    assert "Coloração" not in out
    assert any("event=catalog_unoffered n=1" in r.getMessage() for r in caplog.records)


# ── the total, summed in code ───────────────────────────────────────────────────────────────
def test_total_is_summed_in_code_and_names_both_items():
    hosts = _salon()
    items = C.validate_item_dicts([
        {"kind": "service", "name": "Corte", "value_text": "R$ 40,00",
         "duration_minutes": 30, "host_ids": ["belmira"]},
        {"kind": "service", "name": "Escova", "value_text": "R$ 50,00",
         "duration_minutes": 30, "host_ids": ["belmira"]}], hosts).items
    total, currency, lines = C.catalog_total(["service:corte", "service:escova"], items)
    assert (str(total), currency) == ("90.00", "R$")
    assert [n for n, _ in lines] == ["Corte", "Escova"]


def test_total_refuses_an_item_without_a_value_and_mixed_currencies():
    hosts = _salon()
    items = C.validate_item_dicts([
        {"kind": "product", "name": "Brinde", "value_text": ""},
        {"kind": "product", "name": "Creme", "value_text": "R$ 20,00"},
        {"kind": "product", "name": "Import", "value_text": "US$ 10,00"}], hosts).items
    with pytest.raises(C.CatalogTotalError):
        C.catalog_total(["product:brinde", "product:creme"], items)
    with pytest.raises(C.CatalogTotalError):
        C.catalog_total(["product:creme", "product:import"], items)


# ── the write event: a count, never text ────────────────────────────────────────────────────
def test_catalog_saved_logs_counts_and_a_fixed_door_token(caplog):
    with caplog.at_level(logging.INFO, logger="cogno_praxis.scheduler.catalog"):
        C.record_catalog_saved("ecrã", valid=3, invalid=1)
        C.record_catalog_saved("import", valid=0, invalid=2)
    msgs = [r.getMessage() for r in caplog.records]
    assert any("event=catalog_saved door=ecrã valid=3 invalid=1" in m for m in msgs)
    assert any("event=catalog_saved door=import valid=0 invalid=2" in m for m in msgs)
