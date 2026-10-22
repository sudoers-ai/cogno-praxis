"""The HTML form of a templated e-mail (``render_email_html``) — and the TEXT form, unmoved.

The owner's order (2026-10-22): an e-mail that carries specific data — the month's classes, the
pay values, the total — goes out as HTML with TABLES, beside a text part that says the same. What
is pinned here, one line each:

* the TEXT render is byte for byte the one of before: digests of a corpus of renderings, taken on
  ``f1fc1e9`` and identical on the parent tree ``5d0dc7c`` (#177 does not move the text), with a
  control that proves the digest moves when a byte does;
* ``[aulas]`` is a table with one row per class (Data · Horário when any class has one ·
  Disciplina · Turma); ``[valores_por_bonus]`` a two-column table (Faixa · Valor); ``[disciplinas]``
  a list; ``[total]`` and ``[valor_por_aula]`` bold;
* a template with no data marker in its body renders NO HTML (``""``): the send stays plain text;
* every value and every byte of the tenant's template is escaped, and nothing in the document can
  load anything (no script, no style sheet, no image, no link, no URL);
* the HTML says what the text says: a table is drawn only from rows whose text IS the value the
  text part carries, otherwise the value is shown as escaped text.

Everything here is synthetic: invented professors, an invented school, invented ids.
``render_email_html`` is looked up on the module inside each test, so on a tree without it every
test fails by name rather than the file failing to collect.
"""

from __future__ import annotations

import dataclasses
import hashlib
import html
import json
import re
from datetime import date
from html.parser import HTMLParser

import pytest

import cogno_praxis.email_fields as ef
from cogno_praxis.coordinator import CoordinatorConfig, CoordinatorService, InMemorySpreadsheetStore
from cogno_praxis.email_fields import (
    EmailClass,
    EmailContext,
    email_digest,
    fill_email_fields,
    render_email,
    template_fields,
)

SHEET_X = "X" * 24
SHEET_Y = "Y" * 24
PROF = "Prof Quintino"            # invented
COLLEAGUE = "Prof Ubaldo"          # invented
SCHOOL = "Colégio Horizonte"      # invented
ADDRESS = "quintino@captura.local"  # invented, under a capture domain

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
_HEADER = ["Data", "Dia", "Professor", "Disciplina", "Sala", "Hora"]


def _schedule_x(subject_a: str = "Redes de Computadores", time_last: str = "",
                extra: "tuple[list, ...]" = ()) -> list:
    return [
        _HEADER,
        ["05/09/2026", "Sab", PROF, subject_a, "Verde", "08:00"],
        ["12/09/2026", "Sab", PROF, subject_a, "Verde", "08:00"],
        ["19/09/2026", "Sab", COLLEAGUE, subject_a, "Verde", "08:00"],
        ["26/09/2026", "Sab", PROF, "Cálculo Numérico", "Verde", time_last],
        ["03/10/2026", "Sab", PROF, "Cálculo Numérico", "Verde", "13:30"],
        *extra,
    ]


#: A day with three classes — one with no hour, one listed out of order — and two disciplines whose
#: case-folded order is not their code-point order («banco…» after «Zoologia» by code point).
_SAME_DAY = (["12/09/2026", "Sab", PROF, "banco de dados", "Verde", ""],
             ["12/09/2026", "Sab", PROF, "Zoologia Aplicada", "Verde", "10:00"])


_SCHEDULE_Y = [_HEADER, ["19/09/2026", "Sab", PROF, "Redes de Computadores", "Azul", "13:30"]]
_TODAY = date(2026, 9, 20)


def _svc(*, bonus: bool = True, ibope: "str | None" = None, rules_extra: str = "",
         subject_a: str = "Redes de Computadores", time_last: str = "",
         extra: "tuple[list, ...]" = ()) -> CoordinatorService:
    store = InMemorySpreadsheetStore()
    store.put(SHEET_X, "Secretaria", _schedule_x(subject_a, time_last, extra))
    store.put(SHEET_Y, "Secretaria", _SCHEDULE_Y)
    rows = [["Professor", "Resultado"]] + ([[PROF, ibope]] if ibope is not None else [])
    store.put(SHEET_X, "Resultados IBOPE", rows)
    rules = _RULES + (_BONUS if bonus else "") + rules_extra
    return CoordinatorService(store, CoordinatorConfig(rules), today=lambda: _TODAY)


def _ctx(svc: "CoordinatorService | None" = None, *, month: str = "2026-09",
         conteudo: str = "", **kw) -> EmailContext:
    svc = svc or _svc()
    c = svc.email_context(professor="", role="EMPLOYEE", identity_label=PROF, period=month)
    return dataclasses.replace(c, recipient_name=PROF, recipient_email=ADDRESS,
                               tenant_name=SCHOOL, conteudo=conteudo, today=_TODAY,
                               persona_name="Coordenação", requester_name="Prof Ubaldo", **kw)


# The owner's template SHAPES (2026-10-06), text invented: the class schedule, the invoice e-mail;
# and two more — the total alone, and a template of generic markers only.
T_SCHEDULE = ("Cronograma de aulas — [mes]",
              "Olá, [nome],\n\nSegue o seu cronograma de aulas de [mes] na [empresa]:\n\n"
              "[aulas]\n\nDisciplinas do mês:\n[disciplinas]\n\n[conteudo]\n\n"
              "Atenciosamente,\nCoordenação — [empresa]")
T_INVOICE = ("Emissão de nota fiscal — [mes]",
             "Olá, [nome],\n\nPara a sua nota fiscal de [mes], estes são os valores estimados por "
             "nível de bônus (valor por aula: [valor_por_aula]):\n\n[valores_por_bonus]\n\n"
             "Aulas consideradas:\n[aulas]\n\nAtenciosamente,\n[empresa]")
T_TOTAL = ("Total de [mes]", "Olá, [nome].\nO total do mês é [total].\n[assinatura]")
T_GENERIC = ("Aviso da [empresa]", "Olá, [nome],\n\n[conteudo]\n\nEm [data],\n[assinatura]")


def _html(*args, **kw) -> str:
    return getattr(ef, "render_email_html")(*args, **kw)


def _filled(template, ctx):
    values, missing = fill_email_fields(template_fields(*template), ctx)
    assert missing == (), [m.sentence() for m in missing]
    return values


# ── the TEXT form does not move by a byte ───────────────────────────────────────────────────

def _corpus():
    """``(label, template, context)`` — every bonus world, with and without the response-rate
    condition, a month with classes and one whose single class is in October, a class with no
    hour, and the generic template. Only cases that FILL are rendered."""
    cases = []
    for ibope in ("92", "85", "71", "89,5", None):
        for cond in ("", "IBOPE_MIN_RESPONSE_PCT: 30\n"):
            for bonus in (True, False):
                svc = _svc(bonus=bonus, ibope=ibope, rules_extra=cond)
                tag = f"ibope={ibope}|cond={bool(cond)}|bonus={bonus}"
                for name, tpl in (("schedule", T_SCHEDULE), ("invoice", T_INVOICE),
                                  ("total", T_TOTAL)):
                    free = "Lembre da sala." if "[conteudo]" in tpl[1] else ""
                    for month in ("2026-09", "2026-10"):
                        cases.append((f"{name}|{tag}|{month}", tpl,
                                      _ctx(svc, month=month, conteudo=free)))
    cases.append(("generic", T_GENERIC, _ctx(conteudo="Reunião na sexta.\nTraga o diário.")))
    cases.append(("schedule|hour-everywhere", T_SCHEDULE,
                  _ctx(_svc(time_last="10:00"), conteudo="x")))
    same_day = _svc(ibope="92", extra=_SAME_DAY)
    cases.append(("schedule|same-day", T_SCHEDULE, _ctx(same_day, conteudo="x")))
    cases.append(("invoice|same-day", T_INVOICE, _ctx(same_day)))
    return cases


def _rendered_digests() -> "dict[str, str]":
    out = {}
    for label, tpl, ctx in _corpus():
        values, missing = fill_email_fields(template_fields(*tpl), ctx)
        if missing:
            out[label] = "missing:" + ",".join(sorted(m.field for m in missing))
            continue
        out[label] = email_digest(*render_email(*tpl, values))
    return out


#: Taken on ``f1fc1e9`` with this file's corpus, and identical on the parent tree ``5d0dc7c`` — a
#: landing-time proof:
#: regenerate it only when the text render changes ON PURPOSE.
_BASE_DIGESTS: "dict[str, str]" = {
    "generic":
        "ee8ff3d4c9f860acca342bb3a5c7f94dec262b658238838e23c91630ba491767",
    "invoice|ibope=71|cond=False|bonus=True|2026-09":
        "fc76ea55e3dd4761686132bbc217ca82b1f0055b39ff7f5c1393850de15afa65",
    "invoice|ibope=71|cond=False|bonus=True|2026-10":
        "e838e4ee5f3cc16e41c6f0a764c7bb78a93027db7f92320c4e15e2f7ba90fb65",
    "invoice|ibope=71|cond=True|bonus=True|2026-09":
        "32ce71c81c808b2f17cd040eff58049e0b842a7bbbba6075df26f0c4e3623200",
    "invoice|ibope=71|cond=True|bonus=True|2026-10":
        "bdc22ba7daa416cbc55749588d34a2aba1089b08c0eac89a4d9a640a3d25d096",
    "invoice|ibope=85|cond=False|bonus=True|2026-09":
        "3578ff2402dccf1db7f616e9e7f466077b5d90c108b2daf0752f4aa0feff344b",
    "invoice|ibope=85|cond=False|bonus=True|2026-10":
        "b3661baf2017f49e9082ccef11c40c5290a58be5de2da85a96fb4c75666d4a64",
    "invoice|ibope=85|cond=True|bonus=True|2026-09":
        "0adc1a87ec133b336a93f5d65291ea13f0edd13b8be50f34b0719dbef5849382",
    "invoice|ibope=85|cond=True|bonus=True|2026-10":
        "58556956bb801497eea2be9c172200a9628f68811ed1e1d9e093fb4c918c30fc",
    "invoice|ibope=89,5|cond=False|bonus=True|2026-09":
        "d4f54a4008504122e1909ee47ef9a6d5f35a0c5dd22d88403874001883866a50",
    "invoice|ibope=89,5|cond=False|bonus=True|2026-10":
        "34fe9fbab400998e8f0894099c9a0a05ac553d6d35cb2975b1e484c226471f4f",
    "invoice|ibope=89,5|cond=True|bonus=True|2026-09":
        "1d0d3ce94829cd5cf7b63387962f57a39e9f6d043e0ad7a37d846f4ce17cee58",
    "invoice|ibope=89,5|cond=True|bonus=True|2026-10":
        "b7f8bf9bd6306c40e746b53e9d6e3f1f268fe780c2a93def056fd189f4d8e100",
    "invoice|ibope=92|cond=False|bonus=True|2026-09":
        "e4ddf4090e9adc8f22b8f9943f5140fcfc8afafb7fc7d7b9ec6b401f3080bff5",
    "invoice|ibope=92|cond=False|bonus=True|2026-10":
        "cbecf86b7f34a02df9da36b84aa68460a99ebeddd2d865ceb433e29daac65990",
    "invoice|ibope=92|cond=True|bonus=True|2026-09":
        "c8d07d14bd376aab27345549eb70395b491074ec30a645fc2bac572000c435ec",
    "invoice|ibope=92|cond=True|bonus=True|2026-10":
        "3c959ca493b4adfcf111c5c349c0c42094cc15d5a7e04190c34911f4e9757af7",
    "invoice|ibope=None|cond=False|bonus=True|2026-09":
        "d4f54a4008504122e1909ee47ef9a6d5f35a0c5dd22d88403874001883866a50",
    "invoice|ibope=None|cond=False|bonus=True|2026-10":
        "34fe9fbab400998e8f0894099c9a0a05ac553d6d35cb2975b1e484c226471f4f",
    "invoice|ibope=None|cond=True|bonus=True|2026-09":
        "1d0d3ce94829cd5cf7b63387962f57a39e9f6d043e0ad7a37d846f4ce17cee58",
    "invoice|ibope=None|cond=True|bonus=True|2026-10":
        "b7f8bf9bd6306c40e746b53e9d6e3f1f268fe780c2a93def056fd189f4d8e100",
    "invoice|same-day":
        "33648c5ba72b87532d0b8c6ac4dc30d8e21734260cfb33773c9611d71d3c026f",
    "schedule|hour-everywhere":
        "e0931bf71fa00b8fca486dd430a5e5bff188a9ce844a21fa9291aa1a6e926ddb",
    "schedule|ibope=71|cond=False|bonus=False|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=71|cond=False|bonus=False|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=71|cond=False|bonus=True|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=71|cond=False|bonus=True|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=71|cond=True|bonus=False|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=71|cond=True|bonus=False|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=71|cond=True|bonus=True|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=71|cond=True|bonus=True|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=85|cond=False|bonus=False|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=85|cond=False|bonus=False|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=85|cond=False|bonus=True|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=85|cond=False|bonus=True|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=85|cond=True|bonus=False|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=85|cond=True|bonus=False|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=85|cond=True|bonus=True|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=85|cond=True|bonus=True|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=89,5|cond=False|bonus=False|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=89,5|cond=False|bonus=False|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=89,5|cond=False|bonus=True|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=89,5|cond=False|bonus=True|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=89,5|cond=True|bonus=False|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=89,5|cond=True|bonus=False|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=89,5|cond=True|bonus=True|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=89,5|cond=True|bonus=True|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=92|cond=False|bonus=False|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=92|cond=False|bonus=False|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=92|cond=False|bonus=True|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=92|cond=False|bonus=True|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=92|cond=True|bonus=False|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=92|cond=True|bonus=False|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=92|cond=True|bonus=True|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=92|cond=True|bonus=True|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=None|cond=False|bonus=False|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=None|cond=False|bonus=False|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=None|cond=False|bonus=True|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=None|cond=False|bonus=True|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=None|cond=True|bonus=False|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=None|cond=True|bonus=False|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|ibope=None|cond=True|bonus=True|2026-09":
        "0ff72eaf1d3a65e9ad27cd1e4377a15006353315792e71d736c53dc951c743e4",
    "schedule|ibope=None|cond=True|bonus=True|2026-10":
        "73b8702ef706c711296d13b3962ddfff62d397f1544865cf63294fced282cf70",
    "schedule|same-day":
        "3e7b585e86afa438f25980d7cf7ee6ef41ad24b7f7db45563526149694589d0a",
    "total|ibope=71|cond=False|bonus=False|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=71|cond=False|bonus=False|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
    "total|ibope=71|cond=False|bonus=True|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=71|cond=False|bonus=True|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
    "total|ibope=71|cond=True|bonus=False|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=71|cond=True|bonus=False|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
    "total|ibope=71|cond=True|bonus=True|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=71|cond=True|bonus=True|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
    "total|ibope=85|cond=False|bonus=False|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=85|cond=False|bonus=False|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
    "total|ibope=85|cond=False|bonus=True|2026-09":
        "5951a94992d6a85ce606189a6cf07ac9637171f184265cade495655aa1e5bed1",
    "total|ibope=85|cond=False|bonus=True|2026-10":
        "750d1dcbf907e420f5ed390173422259a2a6292fc68e2e00dc1bdd9cbfc99456",
    "total|ibope=85|cond=True|bonus=False|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=85|cond=True|bonus=False|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
    "total|ibope=85|cond=True|bonus=True|2026-09":
        "5951a94992d6a85ce606189a6cf07ac9637171f184265cade495655aa1e5bed1",
    "total|ibope=85|cond=True|bonus=True|2026-10":
        "750d1dcbf907e420f5ed390173422259a2a6292fc68e2e00dc1bdd9cbfc99456",
    "total|ibope=89,5|cond=False|bonus=False|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=89,5|cond=False|bonus=False|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
    "total|ibope=89,5|cond=True|bonus=False|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=89,5|cond=True|bonus=False|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
    "total|ibope=92|cond=False|bonus=False|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=92|cond=False|bonus=False|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
    "total|ibope=92|cond=False|bonus=True|2026-09":
        "3f274492bcd951b5502d8ba31c5ca89e8543eab8bc503f2ff8edd629b6777f37",
    "total|ibope=92|cond=False|bonus=True|2026-10":
        "c93a5f5ab55b89951a3f28f7352d32302c4c13640bf574df39068e3e834236ae",
    "total|ibope=92|cond=True|bonus=False|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=92|cond=True|bonus=False|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
    "total|ibope=92|cond=True|bonus=True|2026-09":
        "3f274492bcd951b5502d8ba31c5ca89e8543eab8bc503f2ff8edd629b6777f37",
    "total|ibope=92|cond=True|bonus=True|2026-10":
        "c93a5f5ab55b89951a3f28f7352d32302c4c13640bf574df39068e3e834236ae",
    "total|ibope=None|cond=False|bonus=False|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=None|cond=False|bonus=False|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
    "total|ibope=None|cond=True|bonus=False|2026-09":
        "d38af4290bdb82bc95f4f019b5099edb6875532a36c050a562fa055a17d48c10",
    "total|ibope=None|cond=True|bonus=False|2026-10":
        "f8149b800c2e5f569831b5e4dbb004ab7d428d391fc2993505d6d18ecfec094d",
}
#: sha256 of the sorted ``label=digest`` lines above — one value to compare across trees.
_BASE_CORPUS_SHA = "897738494572dffcb7683593cb67aeb867566192bc76fdef51f862c4a0a274b0"


def test_the_text_render_is_byte_for_byte_the_parent_trees():
    got = _rendered_digests()
    rendered = {k: v for k, v in got.items() if not v.startswith("missing:")}
    assert rendered == _BASE_DIGESTS
    # the corpus must RENDER every template shape, not only report what is missing
    assert {k.split("|")[0] for k in rendered} == {"schedule", "invoice", "total", "generic"}
    assert len(rendered) > 40 and len(got) > 100
    lines = "\n".join(f"{k}={v}" for k, v in sorted(got.items()))
    assert hashlib.sha256(lines.encode()).hexdigest() == _BASE_CORPUS_SHA


def test_control_the_digest_moves_when_one_byte_of_the_text_does():
    """The pair of the test above: the same corpus with ONE value changed by one character must
    not match — otherwise the comparison could not see the change it exists for."""
    label, tpl, ctx = next(c for c in _corpus() if c[0].startswith("schedule|ibope=92"))
    values = _filled(tpl, ctx)
    values["aulas"] = values["aulas"].replace("—", "-", 1)
    assert email_digest(*render_email(*tpl, values)) != _BASE_DIGESTS[label]


# ── the HTML form: tables ────────────────────────────────────────────────────────────────────

def _rows(doc: str, table_index: int = 0) -> "list[list[str]]":
    """The cells of each body row of the ``table_index``-th table, as text."""
    table = re.findall(r"<table\b.*?</table>", doc, flags=re.S)[table_index]
    body = re.search(r"<tbody>(.*)</tbody>", table, flags=re.S).group(1)
    return [[html.unescape(re.sub(r"<[^>]+>", "", c)) for c in re.findall(r"<td\b[^>]*>(.*?)</td>", r, flags=re.S)]
            for r in re.findall(r"<tr\b[^>]*>(.*?)</tr>", body, flags=re.S)]


def _head(doc: str, table_index: int = 0) -> "list[str]":
    table = re.findall(r"<table\b.*?</table>", doc, flags=re.S)[table_index]
    return [html.unescape(re.sub(r"<[^>]+>", "", c)) for c in re.findall(r"<th\b[^>]*>(.*?)</th>", table, flags=re.S)]


def test_aulas_is_a_table_with_one_row_per_class_and_the_right_columns():
    ctx = _ctx(_svc(ibope="92"), conteudo="Lembre da sala.")
    doc = _html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    assert doc.count("<table") == 1
    assert _head(doc) == ["Data", "Horário", "Disciplina", "Turma"]
    assert _rows(doc) == [["05/09", "08:00", "Redes de Computadores", "Turma XA_01"],
                          ["12/09", "08:00", "Redes de Computadores", "Turma XA_01"],
                          ["19/09", "13:30", "Redes de Computadores", "Turma YB_02"],
                          ["26/09", "", "Cálculo Numérico", "Turma XA_01"]]
    assert len(_rows(doc)) == len(ctx.classes)


def test_the_hour_column_is_drawn_only_when_some_class_has_an_hour():
    ctx = _ctx(_svc(ibope="92"), month="2026-10", conteudo="x")
    assert all(not c.time for c in ctx.classes) is False   # control: October HAS an hour
    no_hour = dataclasses.replace(ctx, classes=tuple(dataclasses.replace(c, time="")
                                                     for c in ctx.classes))
    doc = _html(*T_SCHEDULE, _filled(T_SCHEDULE, no_hour), no_hour)
    assert _head(doc) == ["Data", "Disciplina", "Turma"]
    assert _rows(doc) == [["03/10", "Cálculo Numérico", "Turma XA_01"]]


def test_valores_por_bonus_is_a_two_column_table_and_the_applied_band_is_marked():
    ctx = _ctx(_svc(ibope="92", rules_extra="IBOPE_MIN_RESPONSE_PCT: 30\n"))
    values = _filled(T_INVOICE, ctx)
    doc = _html(*T_INVOICE, values, ctx)
    assert doc.count("<table") == 2                      # the bands, then the classes
    assert _head(doc, 0) == ["Faixa", "Valor"]
    assert _rows(doc, 0) == [["Sem bônus", "R$ 1.920,00"],
                             ["IBOPE 80–89%", "R$ 2.400,00"],
                             ["IBOPE 90%+", "R$ 2.560,00 ← apurado (IBOPE 92%)"]]
    bands = re.findall(r"<table\b.*?</table>", doc, flags=re.S)[0]
    marked = [r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", bands, flags=re.S) if "apurado" in r]
    assert len(marked) == 1 and "font-weight:700" in marked[0]
    # the condition the bonus hangs on follows the table, as it follows the lines in the text
    seen = html.unescape(doc)
    assert "Condição das regras: o bônus só é devido" in seen
    assert seen.index("</table>") < seen.index("Condição das regras") < seen.index("Aulas consid")


@pytest.mark.parametrize("ibope", ["89,5", None])
def test_no_band_is_marked_when_the_bonus_is_not_determined(ibope):
    ctx = _ctx(_svc(ibope=ibope))
    values, _ = fill_email_fields(("valores_por_bonus",), ctx)
    doc = _html("Valores", "[valores_por_bonus]", values, ctx)
    assert [r[0] for r in _rows(doc)] == ["Sem bônus", "IBOPE 80–89%", "IBOPE 90%+"]
    assert "apurado" not in doc and "font-weight:700" not in doc


def test_disciplinas_is_a_list_and_total_and_valor_por_aula_are_bold():
    ctx = _ctx(_svc(ibope="92"), conteudo="x")
    doc = _html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    # the text's own order: case-folded, so «Cálculo» before «Redes»
    assert re.findall(r"<li\b[^>]*>(.*?)</li>", doc) == ["Cálculo Numérico",
                                                       "Redes de Computadores"]
    plain = _ctx(_svc(ibope="92"))           # no free text: these templates have no [conteudo]
    doc = _html(*T_TOTAL, _filled(T_TOTAL, plain), plain)
    assert "<strong>R$ 2.560,00</strong>" in doc
    doc = _html(*T_INVOICE, _filled(T_INVOICE, plain), plain)
    assert "<strong>R$ 480,00</strong>" in doc


# ── when there is no HTML at all ────────────────────────────────────────────────────────────

def test_a_template_of_generic_markers_renders_no_html():
    """No table to draw: an HTML part would repeat the text in another dress and change how every
    plain e-mail goes out. ``""`` means the send stays the text it was."""
    ctx = _ctx(conteudo="Reunião na sexta.\nTraga o diário.")
    values = _filled(T_GENERIC, ctx)
    assert render_email(*T_GENERIC, values)                  # control: the text DOES render
    assert _html(*T_GENERIC, values, ctx) == ""


def test_a_data_marker_only_in_the_subject_renders_no_html():
    ctx = _ctx(_svc(ibope="92"))
    tpl = ("Total de [mes]: [total]", "Olá, [nome]. Segue o total no assunto.")
    values = _filled(tpl, ctx)
    assert _html(*tpl, values, ctx) == ""
    assert _html("Total", "Olá, [nome]. Total: [total].", values, ctx) != ""   # control


def test_a_company_tag_alone_renders_no_html():
    ctx = _ctx(custom_tags={"horario_atendimento": "Seg a sex\n8h às 17h"})
    tpl = ("Atendimento", "Olá, [nome].\n[horario_atendimento]")
    values = _filled(tpl, ctx)
    assert _html(*tpl, values, ctx) == ""


# ── safe by construction ────────────────────────────────────────────────────────────────────

#: The document's whole alphabet of elements and attributes. Anything outside it — a script, a
#: style sheet, an image, a link, an event handler — fails, whatever text the values carry: text
#: is escaped, so only what the renderer writes can be a tag.
_TAGS = {"html", "head", "meta", "title", "body", "div", "table", "thead", "tbody", "tr", "th",
         "td", "ul", "li", "p", "br", "strong"}
_ATTRS = {"style", "lang", "charset", "name", "content"}
_STYLE_FORBIDDEN = ("url(", "expression", "@import", "javascript", "behavior", "http")


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: "list[tuple[str, list]]" = []
        self.decls: "list[str]" = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, attrs))

    def handle_decl(self, decl):
        self.decls.append(decl)


def _assert_inert(doc: str) -> None:
    parser = _Tags()
    parser.feed(doc)
    parser.close()
    assert parser.decls == ["DOCTYPE html"]
    assert parser.tags, "no element parsed — the check would pass on anything"
    for tag, attrs in parser.tags:
        assert tag in _TAGS, tag
        for name, value in attrs:
            assert name in _ATTRS, (tag, name)
            assert not any(bad in (value or "").lower() for bad in _STYLE_FORBIDDEN), (tag, value)
    metas = [dict(a) for t, a in parser.tags if t == "meta"]
    assert metas == [{"charset": "utf-8"},
                     {"name": "viewport", "content": "width=device-width, initial-scale=1"}]


def test_control_the_inertness_check_refuses_what_it_exists_to_refuse():
    """The pair of every ``_assert_inert`` below: each forbidden shape, written as a TAG (not as
    escaped text), must fail it."""
    shell = ('<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" '
             'content="width=device-width, initial-scale=1"></head><body>{}</body></html>')
    for bad in ("<script>x</script>", '<img src="a.png">', '<a href="https://x.example">a</a>',
                '<link rel="stylesheet">', '<div onclick="x">a</div>', "<style>p{}</style>",
                '<div style="background:url(a.png)">a</div>'):
        with pytest.raises(AssertionError):
            _assert_inert(shell.format(bad))
    _assert_inert(shell.format("&lt;script&gt; src= https://x.example"))   # escaped text passes


def test_a_value_with_markup_comes_out_as_text():
    hostile = '<script>alert(1)</script><b>Redes</b> & "aspas"'
    ctx = _ctx(_svc(ibope="92", subject_a=hostile), conteudo="<img src=https://x.example/a.png>")
    values = _filled(T_SCHEDULE, ctx)
    doc = _html(*T_SCHEDULE, values, ctx)
    _assert_inert(doc)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;&lt;b&gt;Redes&lt;/b&gt; &amp; &quot;aspas&quot;" in doc
    assert hostile in [r[2] for r in _rows(doc)]                 # the cell reads as the text
    assert "&lt;img src=https://x.example/a.png&gt;" in doc


def test_the_tenants_own_template_text_is_escaped_too():
    ctx = _ctx(_svc(ibope="92"))
    tpl = ("Aulas", '<a href="https://x.example">clique</a> <style>p{}</style>\n[aulas]')
    doc = _html(*tpl, _filled(tpl, ctx), ctx)
    _assert_inert(doc)
    assert "&lt;a href=&quot;https://x.example&quot;&gt;clique&lt;/a&gt;" in doc


def test_every_rendering_of_the_corpus_is_inert():
    n = 0
    for _, tpl, ctx in _corpus():
        values, missing = fill_email_fields(template_fields(*tpl), ctx)
        if missing:
            continue
        doc = _html(*tpl, values, ctx)
        if doc:
            n += 1
            _assert_inert(doc)
            assert doc.startswith("<!DOCTYPE html>") and doc.rstrip().endswith("</html>")
    assert n > 20


# ── the HTML says what the text says ────────────────────────────────────────────────────────

def _visible(doc: str) -> str:
    body = doc.split("<body", 1)[1].split(">", 1)[1]          # after the opening tag
    return html.unescape(re.sub(r"<[^>]+>", " ", body))


def test_every_figure_and_class_of_the_text_is_in_the_html_and_no_other():
    ctx = _ctx(_svc(ibope="85", rules_extra="IBOPE_MIN_RESPONSE_PCT: 30\n"))
    values = _filled(T_INVOICE, ctx)
    _, text = render_email(*T_INVOICE, values)
    seen = _visible(_html(*T_INVOICE, values, ctx))
    money = re.compile(r"R\$ [\d.]+,\d{2}")
    assert sorted(money.findall(text)) == sorted(money.findall(seen))
    for c in ctx.classes:
        assert c.when.strftime("%d/%m") in seen and c.subject in seen and c.turma in seen
    heads = {"Data", "Horário", "Disciplina", "Turma", "Faixa", "Valor"}

    def words(s: str) -> "list[str]":
        return [w for w in re.findall(r"\w+", s) if w not in heads]

    assert words(text) == words(seen)


def test_a_value_the_context_does_not_rebuild_is_shown_as_its_text_not_as_a_table():
    """A table is drawn only from rows whose text IS the value the text part carries. A caller
    whose ``values`` came from another read gets the value as escaped text: never a table that
    says something the confirmed text does not."""
    ctx = _ctx(_svc(ibope="92"), conteudo="x")
    values = _filled(T_SCHEDULE, ctx)
    values["aulas"] = "01/09 — Outra Coisa — Turma ZZ"
    doc = _html(*T_SCHEDULE, values, ctx)
    assert "Outra Coisa" in doc and "Redes de Computadores" not in doc.split("<ul")[0]
    assert "<table" not in doc


@pytest.mark.parametrize("name, tpl, tag", [("disciplinas", T_SCHEDULE, "<ul"),
                                            ("valores_por_bonus", T_INVOICE, "<table")])
def test_every_block_falls_back_to_its_text_when_the_context_does_not_rebuild_it(name, tpl, tag):
    ctx = _ctx(_svc(ibope="92"), conteudo="x" if "[conteudo]" in tpl[1] else "")
    values = _filled(tpl, ctx)
    drawn = _html(*tpl, values, ctx)
    values[name] = "Outra linha\ncom <b>marcação</b>"
    doc = _html(*tpl, values, ctx)
    assert "Outra linha<br>\ncom &lt;b&gt;marcação&lt;/b&gt;" in doc
    assert doc.count(tag) == drawn.count(tag) - 1        # that block, and only it, is not drawn


def test_one_pass_a_marker_typed_inside_a_value_stays_text():
    ctx = _ctx(_svc(ibope="92"), conteudo="o [total] e o [aulas]")
    values = _filled(T_SCHEDULE, ctx)
    doc = _html(*T_SCHEDULE, values, ctx)
    assert "o [total] e o [aulas]" in html.unescape(doc)
    assert doc.count("<table") == 1


def test_line_breaks_of_the_text_are_line_breaks_and_a_table_takes_its_own_line():
    ctx = _ctx(_svc(ibope="92"), conteudo="Linha um.\nLinha dois.")
    doc = _html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    assert "Linha um.<br>\nLinha dois." in doc
    # «…na Colégio Horizonte:\n\n[aulas]\n\nDisciplinas…» — one newline on each side of the
    # table is the table's own line; the blank line the text has is kept as one <br>.
    assert "Horizonte:<br>\n<table" in doc
    assert "</table><br>\nDisciplinas do mês:" in doc


def test_render_html_refuses_a_marker_with_no_value_like_the_text_render():
    with pytest.raises(ValueError):
        _html("Aviso", "[aulas]", {}, EmailContext())


def test_it_is_deterministic_and_exported():
    ctx = _ctx(_svc(ibope="92"), conteudo="x")
    values = _filled(T_SCHEDULE, ctx)
    assert _html(*T_SCHEDULE, values, ctx) == _html(*T_SCHEDULE, values, ctx)
    assert "render_email_html" in ef.__all__


# ── which markers have an HTML form: derived, both ways ─────────────────────────────────────

def test_every_providers_marker_has_an_html_form_and_no_generic_one_does():
    forms = getattr(ef, "_HTML_FORMS")
    provided = {f for p in ef.FIELD_PROVIDERS.values() for f in p.field_names}
    assert set(forms) == provided
    assert not set(forms) & set(ef.GENERIC_FIELDS)


def test_the_html_document_is_a_mobile_friendly_shell():
    ctx = _ctx(_svc(ibope="92"), conteudo="x")
    doc = _html(*T_SCHEDULE, _filled(T_SCHEDULE, ctx), ctx)
    assert '<meta charset="utf-8">' in doc
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in doc
    assert "max-width:640px" in doc and "border-collapse:collapse" in doc
    assert "<title>Cronograma de aulas — setembro/2026</title>" in doc


def test_EmailClass_rows_cover_every_class_of_the_context():
    c = EmailClass(when=date(2026, 9, 5), time="", subject="S", turma="T")
    ctx = EmailContext(month="2026-09", classes=(c,), recipient_email=ADDRESS, recipient_name="N",
                       estimate=None)
    values, _ = fill_email_fields(("aulas",), ctx)
    doc = _html("A", "[aulas]", values, ctx)
    assert _rows(doc) == [["05/09", "S", "T"]]
    assert json.dumps(values, ensure_ascii=False)
