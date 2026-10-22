"""The coordination's tools PRINT every value a templated e-mail copies (R-T13, 2026-10-22).

The owner's rule: «preciso de algo genérico» — a persona's e-mail is made with the tenant's own
tags, filled by the persona from the tools it already has, never by a code path of its own. The
coordination's five e-mail values (the classes, the disciplines, the value per class, the value
per bonus band, the total) were computed by a field provider inside the e-mail module; from now
on the persona COPIES them from what ``get_professor_schedule`` and ``estimate_professor_pay``
return, and a value a tool never printed is a value the persona would have to work out — which
is the copy that goes wrong. So the arithmetic stays in the TOOLS' code, and the tools print it:

* the listing line carries the class HOUR when the sheet records one — ``05/09 08:00 · Turma X ·
  Disciplina`` — and the classes of one day are listed by hour (a class with no hour after the
  timed ones), the order the e-mail has always listed them in. A sheet with no hour column lists
  exactly what it always listed (pinned by digest below). The weekday is NOT printed: the e-mail's
  weekday is a derivation of the date, checked by code where the e-mail is composed;
* the pay block prints the value of ONE class (``Valor por aula: R$ X`` = hours per class × the
  rate) beside the two declared factors, in the professor's block and in the faculty-wide one;
* the pay block prints the month's value under EVERY declared bonus band, in every bonus state
  — ``Sem bônus: R$ X`` and one ``<band>: R$ Y`` per band, the determined one marked
  «← apurado (IBOPE N%)» — under ``*Valores por faixa de bônus*``. Before, only the applied band
  (or, with no result, the hypotheses) was printed.

Removing those two additions from every block of the corpus gives the block of the parent tree
byte for byte, and the listings of a sheet with no hour column are the parent's byte for byte:
both are pinned by digests taken on ``ad935b4`` (the base of this change), with a control that
proves the corpus reaches every bonus state.

Everything here is synthetic: invented professors, an invented school, invented ids.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import date

from cogno_praxis.coordinator import (
    CoordinatorConfig,
    CoordinatorService,
    InMemorySpreadsheetStore,
    render_pay_block,
)
from cogno_praxis.coordinator import pay
from cogno_praxis.coordinator.pay import render_faculty_pay_block
from cogno_praxis.coordinator.server import build_server

SHEET_X = "X" * 24
SHEET_Y = "Y" * 24
PROF = "Prof Quintino"            # invented
COLLEAGUE = "Prof Ubaldo"         # invented
COORD = "Coord Zeta"              # invented

_RULES = f"""SPREADSHEETS:
Turma XA_01 = {SHEET_X}
Turma YB_02 = {SHEET_Y}

TAB_SCHEDULE: "Secretaria"
RANGE_SCHEDULE: "A1:F110"
TAB_IBOPE: "Resultados IBOPE"
COLUMN_IBOPE: "Resultado"
COLUMN_DATE: "Data"
COLUMN_PROFESSOR: "Professor"
COLUMN_SUBJECT: "Disciplina"
{{TIME}}HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 120,00
"""
_BONUS = "IBOPE_BONUS: 80-89=30; 90+=40\n"
_COND = "IBOPE_MIN_RESPONSE_PCT: 30\n"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala", "Hora"]
#: Two classes on 12/09 listed BEFORE the 08:00 one would be if the sheet's order were kept: one
#: with no hour, one at 10:00 — so the day's order by hour is visible.
_SCHEDULE_X = [_HEADER,
               ["05/09/2026", "Sab", PROF, "Redes de Computadores", "Verde", "08:00"],
               ["12/09/2026", "Sab", PROF, "banco de dados", "Verde", ""],
               ["12/09/2026", "Sab", PROF, "Zoologia Aplicada", "Verde", "10:00"],
               ["12/09/2026", "Sab", PROF, "Redes de Computadores", "Verde", "08:00"],
               ["19/09/2026", "Sab", COLLEAGUE, "Redes de Computadores", "Verde", "08:00"],
               ["26/09/2026", "Sab", PROF, "Cálculo Numérico", "Verde", ""],
               ["03/10/2026", "Sab", PROF, "Cálculo Numérico", "Verde", "13:30"]]
_SCHEDULE_Y = [_HEADER, ["19/09/2026", "Sab", PROF, "Redes de Computadores", "Azul", "13:30"]]
_TODAY = date(2026, 9, 20)

#: The four bonus worlds and the two with no band at all — every IBOPE result × condition × bands.
_IBOPES = ("92", "85", "71", "89,5", None)
#: The header the band section is printed under — the contract, typed here (the module's constant
#: is pinned to it below), so this file fails on its ASSERTIONS on a tree without the section.
BAND_VALUES_HEADER = "Valores por faixa de bônus"


def _svc(*, bonus: bool = True, ibope: "str | None" = None, cond: bool = False,
         time: bool = True) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    # «No hour» is a sheet with no hour COLUMN: ``COLUMN_TIME`` defaults to «Hora», so a sheet
    # carrying that header has its hour read whether or not the rules declare it (as the
    # calendar export always read it).
    cut = (lambda rows: rows) if time else (lambda rows: [r[:-1] for r in rows])
    store.put(SHEET_X, "Secretaria", cut(_SCHEDULE_X))
    store.put(SHEET_Y, "Secretaria", cut(_SCHEDULE_Y))
    store.put(SHEET_X, "Resultados IBOPE",
              [["Professor", "Resultado"]] + ([[PROF, ibope]] if ibope is not None else []))
    rules = (_RULES.replace("{TIME}", 'COLUMN_TIME: "Hora"\n' if time else "")
             + (_BONUS if bonus else "") + (_COND if cond else ""))
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: _TODAY)


def _text(res) -> str:
    return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")


def _call(svc: CoordinatorService, tool: str, args: dict) -> str:
    async def run() -> str:
        return _text(await build_server(svc).call_tool(tool, args))
    return asyncio.run(run())


def _own_pay(svc: CoordinatorService, month: str = "2026-09") -> str:
    return render_pay_block(svc.estimate_professor_pay(identity_label=PROF, period=month))


# ── the corpus and its digests ─────────────────────────────────────────────────────────────

_LISTING_TOOLS = ("daily_checks", "get_weekly_briefing", "check_deadlines", "check_ibope_status")


def _corpus() -> "list[tuple[str, CoordinatorService]]":
    return [(f"ibope={ibope}|cond={cond}|bonus={bonus}|time={time}",
             _svc(bonus=bonus, ibope=ibope, cond=cond, time=time))
            for ibope in _IBOPES for cond in (False, True) for bonus in (True, False)
            for time in (True, False)]


def _listings(svc: CoordinatorService) -> "list[str]":
    out = []
    for month in ("2026-09", "2026-10", ""):
        for who, role in ((PROF, "EMPLOYEE"), (COORD, "SUPERVISOR")):
            out.append(_call(svc, "get_professor_schedule",
                             {"month": month, "identity_label": who, "role": role,
                              "include_past": True}))
    out += [_call(svc, tool, {"identity_label": PROF, "role": "EMPLOYEE"})
            for tool in _LISTING_TOOLS]
    return out


def _blocks(svc: CoordinatorService) -> "list[str]":
    out = []
    for month in ("2026-09", "2026-10", ""):
        out.append(_own_pay(svc, month))
        out.append(render_faculty_pay_block(svc.estimate_faculty_pay(
            role="SUPERVISOR", identity_label=COORD, period=month)))
        out.append(_call(svc, "estimate_professor_pay",
                         {"period": month, "identity_label": PROF, "role": "EMPLOYEE"}))
        out.append(_call(svc, "estimate_professor_pay",
                         {"period": month, "professor": "*", "identity_label": COORD,
                          "role": "SUPERVISOR"}))
    return out


def _without_the_additions(block: str) -> str:
    """``block`` with the two things this change ADDED removed: the ``Valor por aula`` line, and
    each ``*Valores por faixa de bônus*`` section (its header, its lines, the blank line above)."""
    lines = block.split("\n")
    out: "list[str]" = []
    skipping = False
    for ln in lines:
        if skipping:
            if ln:
                continue
            skipping = False
        if ln == f"*{BAND_VALUES_HEADER}*":
            if out and out[-1] == "":
                out.pop()
            skipping = True
            continue
        if ln.startswith("Valor por aula: "):
            continue
        out.append(ln)
    # A section that ended the block took the blank line before the next one with it; keep
    # the separation the parent had between the bonus section and what followed.
    text = "\n".join(out)
    return re.sub(r"\n(?=\*Carga horária total das disciplinas\*)", "\n\n", text) \
        if "\n\n*Carga" not in text and "*Carga" in text else text


def _digest(parts: "list[str]") -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:16]


#: Taken on ``ad935b4`` (the base of this change) by running ``_listings``/``_blocks`` there.
BASE_UNTIMED_LISTINGS = "5fed384fef83acf4"
BASE_BLOCKS = "19cd89ab8d48179c"


def test_a_sheet_with_no_hour_lists_exactly_what_it_always_listed():
    parts = [out for label, svc in _corpus() if label.endswith("time=False")
             for out in _listings(svc)]
    # Control: the corpus holds listings with classes in them, none of them with an hour.
    assert sum("Redes de Computadores" in p for p in parts) >= 10
    assert not any(re.search(r"\d\d/\d\d \d\d:\d\d", p) for p in parts)
    assert _digest(parts) == BASE_UNTIMED_LISTINGS


def test_removing_the_two_additions_gives_the_parent_block_byte_for_byte():
    parts, states = [], set()
    for _label, svc in _corpus():
        est = svc.estimate_professor_pay(identity_label=PROF, period="2026-09")
        states.add(est.bonus_state if est.tiers else "no_bands")
        parts += [_without_the_additions(b) for b in _blocks(svc)]
    # Control: the corpus reaches every bonus world and the one with no band at all.
    assert states == {"applied", "below", "gap", "not_found", "no_bands"}
    assert _digest(parts) == BASE_BLOCKS


# ── what the persona copies, printed ───────────────────────────────────────────────────────

def test_the_listing_line_carries_the_hour_and_the_day_is_in_hour_order():
    out = _call(_svc(), "get_professor_schedule",
                {"month": "2026-09", "identity_label": PROF, "role": "EMPLOYEE",
                 "include_past": True})
    assert ("*Setembro de 2026*\n"
            "- 05/09 08:00 · Turma XA_01 · Redes de Computadores\n"
            "- 12/09 08:00 · Turma XA_01 · Redes de Computadores\n"
            "- 12/09 10:00 · Turma XA_01 · Zoologia Aplicada\n"
            "- 12/09 · Turma XA_01 · banco de dados\n"
            "- 19/09 13:30 · Turma YB_02 · Redes de Computadores\n"
            "- 26/09 · Turma XA_01 · Cálculo Numérico") in out


def test_the_daily_digest_door_carries_the_hour_too():
    from cogno_praxis.coordinator import daily_checks_text, status_args
    svc = _svc()
    dc = svc.daily_checks(identity_label=PROF, role="EMPLOYEE")
    # 20/09 has no class of this professor: the door is reached and renders through the args.
    assert "time_of" in status_args(svc)
    assert daily_checks_text(dc, **status_args(svc)) == _call(
        svc, "daily_checks", {"identity_label": PROF, "role": "EMPLOYEE"})


def test_the_pay_block_prints_the_value_of_one_class():
    # 4 h per class × R$ 120,00 per hour.
    assert "Horas por aula declaradas nas regras: 4 h\nValor por aula: R$ 480,00" in _own_pay(_svc())
    faculty = render_faculty_pay_block(_svc().estimate_faculty_pay(
        role="SUPERVISOR", identity_label=COORD, period="2026-09"))
    assert "Horas por aula declaradas nas regras: 4 h\nValor por aula: R$ 480,00" in faculty


#: The professor's September: 6 classes × 4 h = 24 h → base R$ 2.880,00; +R$ 30,00/h → 3.600,00;
#: +R$ 40,00/h → 3.840,00.
_BANDS = {
    "92": ("Sem bônus: R$ 2.880,00\nIBOPE 80–89%: R$ 3.600,00\n"
           "IBOPE 90%+: R$ 3.840,00 ← apurado (IBOPE 92%)"),
    "85": ("Sem bônus: R$ 2.880,00\nIBOPE 80–89%: R$ 3.600,00 ← apurado (IBOPE 85%)\n"
           "IBOPE 90%+: R$ 3.840,00"),
    "71": ("Sem bônus: R$ 2.880,00 ← apurado (IBOPE 71%)\nIBOPE 80–89%: R$ 3.600,00\n"
           "IBOPE 90%+: R$ 3.840,00"),
    "89,5": "Sem bônus: R$ 2.880,00\nIBOPE 80–89%: R$ 3.600,00\nIBOPE 90%+: R$ 3.840,00",
    None: "Sem bônus: R$ 2.880,00\nIBOPE 80–89%: R$ 3.600,00\nIBOPE 90%+: R$ 3.840,00",
}


def test_the_pay_block_prints_every_band_in_every_bonus_state():
    for ibope, lines in _BANDS.items():
        for cond in (False, True):
            block = _own_pay(_svc(ibope=ibope, cond=cond))
            assert f"*{BAND_VALUES_HEADER}*\n{lines}" in block, (ibope, cond)


def test_the_header_is_the_modules_one():
    assert getattr(pay, "BAND_VALUES_HEADER", None) == BAND_VALUES_HEADER


def test_no_band_declared_prints_no_band_section():
    assert BAND_VALUES_HEADER not in _own_pay(_svc(bonus=False, ibope="92"))
