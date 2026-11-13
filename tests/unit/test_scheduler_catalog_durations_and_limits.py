"""The catalog import reads a duration WHOLE, names people (not specialties), and refuses an
oversized batch out loud.

Three behaviours, each measured on the import door before this test existed:

* «1 h 30 min», «2 h e 30 min» and «1 hora e 30 minutos» were stored as 60 / 120 / 60 minutes —
  only the FIRST hour/minute unit of the phrase was read — and passed as valid (a multiple of 30).
  The agenda would book a 90-minute service as an hour. A half written in words («1 hora e meia»)
  was read as one hour the same way.
* The «who performs it» cell went through the booking resolver's third tier, the SPECIALTY: a
  cell reading «manicure» linked the service to the only professional whose specialty is
  Manicure — and would move it to someone else the day a second one joins.
* A batch over :data:`MAX_ITEMS` came back with no valid item AND no invalid line, so a door that
  stored it wiped the stored catalog and reported «0 valid, 0 invalid».

Every name here is invented.
"""
from __future__ import annotations

import pytest

from cogno_praxis.scheduler.catalog import (
    MAX_ITEMS,
    REASON_DURATION_NOT_MULTIPLE,
    REASON_PROFESSIONAL_NOT_FOUND,
    REASON_TOO_MANY,
    parse_catalog_block,
    validate_item_dicts,
)
from cogno_praxis.scheduler.names import host_candidates
from cogno_praxis.scheduler.store import Host

_HOSTS = [Host("h-belmira", "Belmira Quostral", "Manicure"),
          Host("h-zelinda", "Zelinda Marquesi Toro", "Cabeleireira")]


def _block(duration: str, who: str = "Belmira") -> str:
    return ("SERVIÇOS (nome | duração | valor | profissionais):\n"
            f"- Escova modelada | {duration} | R$ 80,00 | {who}\n")


@pytest.mark.parametrize("duration,minutes", [
    ("1 h 30 min", 90), ("1h 30min", 90), ("2 h e 30 min", 150), ("1 hora e 30 minutos", 90),
    ("90 min", 90), ("2 horas", 120), ("1,5 h", 90),
])
def test_every_hour_and_minute_of_the_phrase_counts(duration, minutes):
    parse = parse_catalog_block(_block(duration), _HOSTS)
    assert [it.duration_minutes for it in parse.items] == [minutes], parse.invalid


@pytest.mark.parametrize("duration", ["1 hora e meia", "1h30", "1h30min"])
def test_a_duration_the_reader_cannot_read_whole_is_invalid_not_shortened(duration):
    parse = parse_catalog_block(_block(duration), _HOSTS)
    assert parse.items == ()
    assert [i.reason for i in parse.invalid] == [REASON_DURATION_NOT_MULTIPLE]


def test_the_who_cell_names_people_not_a_specialty():
    parse = parse_catalog_block(_block("30 min", who="manicure"), _HOSTS)
    assert parse.items == ()
    assert [(i.reason, i.name) for i in parse.invalid] == [(REASON_PROFESSIONAL_NOT_FOUND, "manicure")]


def test_control_the_who_cell_still_takes_a_name_and_the_booking_resolver_keeps_the_specialty():
    parse = parse_catalog_block(_block("30 min", who="Belmira"), _HOSTS)
    assert [it.host_ids for it in parse.items] == [("h-belmira",)]
    assert [h.host_id for h in host_candidates("manicure", list(_HOSTS))] == ["h-belmira"]
    assert host_candidates("manicure", list(_HOSTS), by_role=False) == []


def test_a_batch_over_the_limit_is_refused_and_says_so():
    many = [{"kind": "product", "name": f"Óleo Vendrim {n}", "value_text": "R$ 10,00"}
            for n in range(MAX_ITEMS + 1)]
    parse = validate_item_dicts(many, _HOSTS)
    assert parse.items == ()
    assert [i.reason for i in parse.invalid] == [REASON_TOO_MANY]
    assert parse.refused


def test_control_a_batch_at_the_limit_is_kept():
    many = [{"kind": "product", "name": f"Óleo Vendrim {n}", "value_text": "R$ 10,00"}
            for n in range(MAX_ITEMS)]
    parse = validate_item_dicts(many, _HOSTS)
    assert len(parse.items) == MAX_ITEMS and not parse.refused


def test_a_paste_with_no_valid_line_is_refused_but_an_empty_batch_is_not():
    broken = parse_catalog_block("- Escova modelada | 60 min | R$ 80,00 | Belmira\n", _HOSTS)
    assert broken.items == () and broken.invalid and broken.refused       # no header: out of section
    assert not parse_catalog_block("", _HOSTS).refused                    # nothing written: a clear
    assert not validate_item_dicts([], _HOSTS).refused
