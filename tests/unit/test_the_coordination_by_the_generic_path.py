"""The coordination's e-mail by the GENERIC path is today's e-mail, byte for byte (R-T13).

The owner's rule (2026-10-22): «preciso de algo genérico. Quando entrar uma persona nova, faço
via tags personalizadas, senão teria que fazer via código» — and asked that the coordination
follow that rule. The coordination's five e-mail values (``[aulas]``, ``[disciplinas]``,
``[valor_por_aula]``, ``[valores_por_bonus]``, ``[total]``) were filled by a field provider from
``CoordinatorService.email_context``. Now they are the tenant's FREE tags, and the persona fills
them by COPYING what its two tools return. This file is the proof that the path changed and the
e-mail did not:

1. the REAL tools (``get_professor_schedule``, ``estimate_professor_pay``) run over a corpus that
   reaches every bonus state, with and without the response-rate condition, with and without
   bands, a class with no hour and the classes of two months;
2. a scripted executor COPIES the values from their outputs — records where the tool lists rows,
   text otherwise — and computes nothing but the weekday and the month's name of each class,
   the two derivations the composer checks (:func:`record_cells_unverified`). Every cell it passes
   is verified: literal in one of the two reads, or a correct derivation;
3. the generic fill renders them; the digest of every tag's text over the corpus is the one the
   provider produced on ``ad935b4`` (the base of this stack), taken by running the provider there
   — and so are the HTML tables, the ``Data`` column included: the read prints ``dd/mm`` and the
   renderer adds the year of the send's month (``dd/mm/aa``, the owner's model), a derivation it
   checks (the Director's correction, 2026-10-22).

What DIVERGES is listed, tag by tag, and each divergence is applied to the generic side by a
named transformation before the comparison, so the digest proves that it is the ONLY difference:

* ``[valores_por_bonus]`` — the lines of the response-rate CONDITION are not records: the
  provider ended the value with them, the generic value does not. A tenant writes the condition
  in its template (or in a fixed tag).
* ``[valores_por_bonus]`` in HTML — the condition paragraph after the table, for the same reason.
* ``[total]`` and ``[valor_por_aula]`` in HTML — the provider made an e-mail with either of them
  HTML, the figure in bold by its NAME. The generic path draws HTML only for an e-mail that
  carries a list of records, and bolds nothing by name: such an e-mail goes out as the text it
  always was (its text is identical).
* A value the tools cannot give is MISSING on both paths: the bands without a declared band, the
  total while the bonus is undetermined. The provider's sentence named the reason; the generic
  one asks with the tenant's hint (the free tag's question).

Everything here is synthetic: invented professors, an invented school, invented ids.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import re
from datetime import date

import cogno_praxis.email_fields as ef
from cogno_praxis.coordinator import CoordinatorConfig, CoordinatorService, InMemorySpreadsheetStore
from cogno_praxis.coordinator.server import build_server
from cogno_praxis.email_fields import (EmailContext, fill_email_fields, render_email_forms,
                                       template_fields)

SHEET_X = "X" * 24
SHEET_Y = "Y" * 24
PROF = "Prof Quintino"            # invented
COLLEAGUE = "Prof Ubaldo"         # invented
SCHOOL = "Colégio Horizonte"      # invented
ADDRESS = "quintino@captura.local"  # invented, under a capture domain
TODAY = date(2026, 9, 20)

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
COLUMN_TIME: "Hora"
HOURS_PER_CLASS: 4
PAY_RATE_PER_HOUR: 120,00
"""
_BONUS = "IBOPE_BONUS: 80-89=30; 90+=40\n"
_COND = "IBOPE_MIN_RESPONSE_PCT: 30\n"
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala", "Hora"]


def _svc(*, bonus: bool, ibope: "str | None", cond: bool, time_last: str) -> CoordinatorService:
    """The corpus the provider's digests were taken over on ``ad935b4`` — the same rows, rules and
    clock (a day with three classes, one with no hour; a class in the second month)."""
    store = InMemorySpreadsheetStore()
    store.put(SHEET_X, "Secretaria", [
        _HEADER,
        ["05/09/2026", "Sab", PROF, "Redes de Computadores", "Verde", "08:00"],
        ["12/09/2026", "Sab", PROF, "Redes de Computadores", "Verde", "08:00"],
        ["19/09/2026", "Sab", COLLEAGUE, "Redes de Computadores", "Verde", "08:00"],
        ["26/09/2026", "Sab", PROF, "Cálculo Numérico", "Verde", time_last],
        ["03/10/2026", "Sab", PROF, "Cálculo Numérico", "Verde", "13:30"],
        ["12/09/2026", "Sab", PROF, "banco de dados", "Verde", ""],
        ["12/09/2026", "Sab", PROF, "Zoologia Aplicada", "Verde", "10:00"]])
    store.put(SHEET_Y, "Secretaria",
              [_HEADER, ["19/09/2026", "Sab", PROF, "Redes de Computadores", "Azul", "13:30"]])
    store.put(SHEET_X, "Resultados IBOPE",
              [["Professor", "Resultado"]] + ([[PROF, ibope]] if ibope is not None else []))
    rules = _RULES + (_BONUS if bonus else "") + (_COND if cond else "")
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: TODAY)


#: The corpus, in the order the provider's digests were taken in.
_CASES = [(ibope, cond, bonus, tl, month)
          for ibope in ("92", "85", "71", "89,5", None) for cond in (False, True)
          for bonus in (True, False) for tl in ("", "10:00") for month in ("2026-09", "2026-10")]
FIVE = ("aulas", "disciplinas", "valor_por_aula", "valores_por_bonus", "total")

#: The provider's outputs on ``ad935b4``, digested over ``_CASES`` (a MISSING value as
#: «MISSING»; a form the provider could not fill as «ABSENT»).
BASE_TEXT = {
    "aulas": "6a0432d8cd93a10d",
    "disciplinas": "b5ab60d3117b375b",
    "valor_por_aula": "4a793650ea589a26",
    "valores_por_bonus": "c0c6b16c73f3533c",
    "total": "5ae989f6d4abf1a0",
}
#: Templates of ONE value each, and the digests of their text and HTML forms on ``ad935b4``.
_FORM_BODIES = {
    "aulas": "Olá, [nome],\n\n[aulas]\n\n[empresa]",
    "disciplinas": "Olá, [nome],\n\n[disciplinas]",
    "bonus": "Olá, [nome],\n\n[valores_por_bonus]",
    "total": "Olá, [nome].\nO total é [total].",
    "vpa": "Olá.\nValor por aula: [valor_por_aula]",
}
BASE_FORMS = {
    ("aulas", "text"): "7cb4dc6fde232cca", ("aulas", "html"): "9e32bf0309c060f7",
    ("disciplinas", "text"): "aa31f66cd69cf3e1", ("disciplinas", "html"): "196c42318c7b6d07",
    ("bonus", "text"): "db91354d0e1d4ea4", ("bonus", "html"): "28dcdfd106f23500",
    ("total", "text"): "dfffe70bd2a72029", ("vpa", "text"): "0ce7db5b4c71d59b",
}


def _digest(parts: "list[str]") -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:16]


def _text(res) -> str:
    return "\n".join(b.text for b in res[0] if getattr(b, "type", None) == "text")


def _reads(svc: CoordinatorService, month: str) -> "tuple[str, str]":
    """The persona's two reads this turn, as the tools return them."""
    async def run() -> "tuple[str, str]":
        mcp = build_server(svc)
        sched = _text(await mcp.call_tool("get_professor_schedule", {
            "month": month, "identity_label": PROF, "role": "EMPLOYEE", "include_past": True}))
        pay = _text(await mcp.call_tool("estimate_professor_pay", {
            "period": month, "identity_label": PROF, "role": "EMPLOYEE"}))
        return sched, pay
    return asyncio.run(run())


# ── the scripted executor: it COPIES, and derives only the weekday and the month's name ──────

_LINE = re.compile(r"^- (\d\d/\d\d)(?: (\d\d:\d\d))? · (.+?) · (.+)$")
#: What a model knows without a tool: the names of the months and of the weekdays.
_MONTHS = ("", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
           "setembro", "outubro", "novembro", "dezembro")
_WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def _executor(sched: str, pay: str, month: str) -> "dict[str, object]":
    """What a persona that READ the two tools passes in ``valores``."""
    year = int(month[:4])
    rows = [m.groups() for m in map(_LINE.match, sched.splitlines()) if m]
    timed = any(time for _day, time, _turma, _subject in rows)
    aulas = []
    for day, time, turma, subject in rows:
        when = date(year, int(day[3:]), int(day[:2]))
        record = {"mês": _MONTHS[when.month], "dia": _WEEKDAYS[when.weekday()], "data": day}
        if timed:
            record["horário"] = time or ""
        record.update({"disciplina": subject, "turma": turma})
        aulas.append(record)
    out: "dict[str, object]" = {}
    if aulas:
        out["aulas"] = aulas
        out["disciplinas"] = [{"disciplina": s} for s in sorted(
            {r["disciplina"] for r in aulas}, key=lambda s: (s.casefold(), s))]
    lines = pay.splitlines()
    for ln in lines:
        if ln.startswith("Valor por aula: "):
            out["valor_por_aula"] = ln.split(": ", 1)[1]
    header = "*Valores por faixa de bônus*"
    if header in lines:
        bands, i = [], lines.index(header) + 1
        while i < len(lines) and lines[i]:
            label, value = lines[i].split(": ", 1)
            bands.append({"faixa": label, "valor": value})
            i += 1
        out["valores_por_bonus"] = bands
    if "*Total*" in lines:
        out["total"] = lines[lines.index("*Total*") + 1]
    elif any(ln.startswith("As regras deste tenant não declaram nenhuma faixa") for ln in lines):
        out["total"] = lines[lines.index("*Base*") + 1].split(" · ")[1]   # no bonus: the base IS it
    return out


def _condition(pay: str) -> str:
    return next((ln for ln in pay.splitlines() if ln.startswith("Condição das regras:")), "")


def _run():
    """``[(case, reads, values, ctx)]`` over the corpus — the generic path, once."""
    out = []
    for ibope, cond, bonus, tl, month in _CASES:
        sched, pay = _reads(_svc(bonus=bonus, ibope=ibope, cond=cond, time_last=tl), month)
        values = _executor(sched, pay, month)
        ctx = EmailContext(recipient_name=PROF, recipient_email=ADDRESS, tenant_name=SCHOOL,
                           month=month, today=TODAY, persona_name="Coordenação",
                           requester_name=COLLEAGUE, custom_tags={n: "" for n in FIVE},
                           free_tag_values=values)
        out.append(((ibope, cond, bonus, tl, month), (sched, pay), values, ctx))
    return out


_RUN: "list | None" = None


def _corpus():
    global _RUN
    if _RUN is None:
        _RUN = _run()
    return _RUN


# ── the proof ──────────────────────────────────────────────────────────────────────────────

def test_every_value_the_executor_passes_is_literal_or_a_checked_derivation():
    unverified = getattr(ef, "record_cells_unverified", None)
    assert unverified is not None, "the record grammar's check is part of the contract"
    checked = derived = 0
    for (*_c, month), (sched, pay), values, _ctx in _corpus():
        def literal(cell: str) -> bool:
            return cell in sched or cell in pay
        for name, value in values.items():
            if isinstance(value, list):
                assert unverified(value, month=month, is_literal=literal) == (), name
                checked += sum(1 for r in value for v in r.values() if v)
                derived += sum(1 for r in value for k, v in r.items()
                               if k in ("dia", "mês") and v and not literal(v))
            else:
                assert literal(value), (name, value)
    # Control: the corpus passes records, and some of their cells pass ONLY as derivations
    # (the weekday is printed by no tool).
    assert checked > 1000 and derived > 100


def test_the_text_of_every_tag_is_the_providers_byte_for_byte():
    for name in FIVE:
        parts = []
        for (_i, cond, _b, _tl, _m), (_s, pay), values, ctx in _corpus():
            got, missing = fill_email_fields([name], ctx)
            text = "MISSING" if any(m.field == name for m in missing) else got[name]
            if name == "valores_por_bonus" and text != "MISSING" and cond:
                # DIVERGENCE (declared): the condition lines are not records.
                text += "\n\n" + _condition(pay)
            parts.append(text)
        assert _digest(parts) == BASE_TEXT[name], name


def _forms(tname: str):
    body = _FORM_BODIES[tname]
    for (_i, cond, _b, _tl, month), (_s, pay), _values, ctx in _corpus():
        vals, missing = fill_email_fields(template_fields("Assunto", body), ctx)
        if missing:
            yield None, None, cond, month, pay
            continue
        _subject, text, doc = render_email_forms("Assunto", body, vals, ctx)
        yield text, doc, cond, month, pay


def test_the_text_forms_are_the_providers_byte_for_byte():
    for tname in _FORM_BODIES:
        parts = []
        for text, _doc, cond, _month, pay in _forms(tname):
            if text is not None and tname == "bonus" and cond:
                text += "\n\n" + _condition(pay)          # DIVERGENCE (declared), as above
            parts.append("ABSENT" if text is None else text)
        assert _digest(parts) == BASE_FORMS[(tname, "text")], tname


def test_the_html_tables_are_the_providers_but_for_the_declared_divergences():
    for tname in ("aulas", "disciplinas", "bonus"):
        parts = []
        for _text, doc, cond, month, pay in _forms(tname):
            if doc is not None and tname == "bonus" and cond:
                # DIVERGENCE (declared): the condition paragraph after the table.
                doc = doc.replace("</table>", '</table><p style="margin:0 0 12px">'
                                  + html.escape(_condition(pay), quote=True) + "</p>", 1)
            parts.append("ABSENT" if doc is None else doc)
        assert _digest(parts) == BASE_FORMS[(tname, "html")], tname


def test_a_figure_alone_goes_out_as_text_never_bold_by_its_name():
    # DIVERGENCE (declared): the provider drew an HTML e-mail for [total]/[valor_por_aula], the
    # figure bold by name; the generic path draws HTML only for an e-mail carrying records.
    for tname in ("total", "vpa"):
        docs = [doc for _t, doc, *_ in _forms(tname) if doc is not None]
        assert docs and all(doc == "" for doc in docs), tname


def test_control_the_digest_sees_one_byte():
    parts = []
    for *_rest, values, ctx in _corpus()[:1]:
        got, _missing = fill_email_fields(["aulas"], ctx)
        parts.append(got.get("aulas", "").replace("08:00", "08:01", 1))
    assert _digest(parts) != _digest([fill_email_fields(["aulas"], _corpus()[0][3])[0].get("aulas", "")])
