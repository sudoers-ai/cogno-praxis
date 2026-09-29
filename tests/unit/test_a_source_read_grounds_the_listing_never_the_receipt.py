"""A read of the business's own DOCUMENT is a source — declared by the host, admitted by VALUE.

The defect, as a shape (every name and figure below is invented; none belongs to a tenant):
a contact asks the BOOKKEEPER about the rents the business wrote in its document. The executor
calls the host's document read, the draft quotes the three figures of the section asked about,
and the judge approves. Then this net rewrites the reply into «Deixa eu consultar o que está
registrado…», and the contact gets no answer:

* rule (1) ``fabricated_entry`` — the document uses the ATTRIBUTIVE participle and the draft
  copies it, always POST-nominal and never opening a line or a sentence («… mensal registrada»
  4 times, «… meses registrados» 4 times, one participle per draft); a turn that read no LEDGER
  reads that as a receipt (8 of 10 turns on a rehearsal tenant, 2026-09-29);
* rule (3) ``conjured_totals`` — money beside a totals word with no ledger read, «líquido» in one
  and «total» in the other (2 of 10) — and **4 of the 8 above carry «líquido» too**, so excusing
  rule (1) alone would have handed those four to rule (3): the fix has to cover both at once.

The forms were read off the persisted drafts with this repo's own matchers (the net reads the
VOICED reply, which is not persisted; the draft is the closest persisted text and matches the
same rule in all ten). ``is_read_query`` was ``true`` in all ten and is NOT a gate here.

The fix (``ground_reply(..., source_reads=)``): the HOST declares which of its tools read the
business's material — never a name this repo knows — and a reply whose EVERY money value is
written in the result of a successful call to one of them is grounded in it. It excuses the
attributive participle of rule (1) and the totals of rule (3), and nothing else. Pinned beside
it, everything it must NOT open:

* the RECEIPT shape «Registrado! R$ 150,00» — the participle opening its clause — even when the
  document holds R$ 150,00 (a document grounds a figure, never an act);
* the EXPLICIT claim «Registrei R$ 150,00», «foi registrada»;
* a value the document does not hold: a sum of its rows, a year worked out from a month, ONE of
  three;
* a read the host did not declare, a read that failed, a ledger write called this turn;
* no declaration at all → every verdict exactly as before (the digest below).

Where each twin has its broken world, it is asserted right beside the fixed one.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from cogno_praxis.bookkeeper.grounding import ground_reply
from cogno_praxis.declared_values import declared_values
from cogno_praxis.grounding import ToolCall
from cogno_praxis.scheduler.grounding import ground_reply as sched_ground

# The host's document read, by a name this repo has never heard of: the exemption must come
# from the DECLARATION, so the tests never use the name the host happens to ship.
DOC_READ = "read_business_documents"
DECLARED = frozenset({DOC_READ})

# ── an invented business document, LONG: the section asked about sits past char 4000 ──────────
_FILLER = "".join(
    f"## {n}. Seção {n} do relatório\n"
    + "Texto corrido do relatório patrimonial do Edifício Ipê, sem valores nesta parte. " * 6
    + "\n\n" for n in range(1, 10))
_SECTION_10 = (
    "## 10. Aluguéis\n"
    "Receita mensal registrada por unidade (contratos vigentes):\n"
    "- Loja do térreo: R$ 3.715\n"
    "- Sala do 1º andar: R$ 2.460\n"
    "- Apartamento do 2º andar: R$ 1.385\n"
    "Total mensal: R$ 7.560\n"
    "Líquido mensal, depois da taxa de administração: R$ 6.955\n"
    "Média dos últimos 12 meses registrados: R$ 7.410\n\n"
    "## 11. Tarifas\n"
    "Tarifa de vistoria: R$ 150,00\n")
DOCUMENT = _FILLER + _SECTION_10

READ = [ToolCall(tool=DOC_READ, ok=True, result=DOCUMENT)]


def _rule(reply, *, tools=READ, source_reads=DECLARED, locale="pt", **kw):
    v = ground_reply(reply, tools=list(tools), locale=locale, source_reads=source_reads, **kw)
    return v.rule if v else None


def _main(reply, *, tools=READ, locale="pt", **kw):
    """The broken world: exactly the call a host made before the parameter existed."""
    v = ground_reply(reply, tools=list(tools), locale=locale, **kw)
    return v.rule if v else None


def test_the_fixture_puts_every_figure_past_a_4000_char_excerpt():
    """The figures live where a trace excerpt (4000 chars) cannot see them — the reason the host
    hands the WHOLE result over, and the reason this rule reads all of it."""
    for fig in ("R$ 3.715", "R$ 2.460", "R$ 1.385", "R$ 7.560", "R$ 6.955", "R$ 7.410",
                "R$ 150,00"):
        assert DOCUMENT.index(fig) > 4000, fig


# ── the twins: the ten measured turns, in their FORM ─────────────────────────────────────────
# 8 by rule (1): the post-nominal participle copied from the document, beside its money —
# «… mensal registrada» ×4, «… meses registrados» ×4, and «líquido» in four of the eight.
ATTRIBUTIVE_TWINS = [
    # «… mensal registrada»
    "Segundo o documento, a receita mensal registrada é de R$ 3.715,00 (loja), R$ 2.460,00 "
    "(sala) e R$ 1.385,00 (apartamento).",
    "A receita mensal registrada por unidade: loja R$ 3.715, sala R$ 2.460 e apartamento "
    "R$ 1.385 — líquido de R$ 6.955 depois da taxa de administração.",
    "Pelo relatório, a receita mensal registrada é R$ 3.715,00 da loja, R$ 2.460,00 da sala e "
    "R$ 1.385,00 do apartamento; o valor líquido é R$ 6.955,00.",
    "Segue a receita mensal registrada no documento:\n\n- **Loja do térreo:** R$ 3.715,00\n"
    "- **Sala do 1º andar:** R$ 2.460,00\n- **Apartamento do 2º andar:** R$ 1.385,00",
    # «… meses registrados»
    "Na média dos últimos 12 meses registrados, os aluguéis renderam R$ 7.410,00 por mês.",
    "Claro! 😊 Nos 12 meses registrados no documento, a média foi de R$ 7.410,00 por mês, com "
    "líquido mensal de R$ 6.955,00.",
    "Considerando os meses registrados, a loja rende R$ 3.715,00, a sala R$ 2.460,00 e o "
    "apartamento R$ 1.385,00, com líquido de R$ 6.955,00.",
    "Loja do térreo: R$ 3.715,00\nSala do 1º andar: R$ 2.460,00\nApartamento do 2º andar: "
    "R$ 1.385,00\n(média dos meses registrados: R$ 7.410,00)",
]
# 2 by rule (3): money beside a totals word, no participle — a total the document WROTE.
TOTALS_TWINS = [
    "Pelo documento, o líquido mensal dos aluguéis é R$ 6.955,00: loja R$ 3.715,00, sala "
    "R$ 2.460,00 e apartamento R$ 1.385,00.",
    "O total mensal de aluguéis do Edifício Ipê é R$ 7.560,00: loja R$ 3.715,00, sala "
    "R$ 2.460,00 e apartamento R$ 1.385,00.",
]


@pytest.mark.parametrize("reply", ATTRIBUTIVE_TWINS)
def test_the_attributive_listing_read_from_the_document_is_KEPT(reply):
    assert _main(reply) == "fabricated_entry"          # the broken world: the measured rewrite
    assert _rule(reply) is None                         # the fixed one: the contact's answer


@pytest.mark.parametrize("reply", TOTALS_TWINS)
def test_the_totals_the_document_wrote_are_not_conjured(reply):
    assert _main(reply) == "conjured_totals"
    assert _rule(reply) is None


def test_the_twins_are_ten_eight_and_two_in_the_measured_forms():
    from cogno_praxis.bookkeeper.grounding import (_RECORDED_ATTRIBUTIVE_RE, _RECORDED_RE,
                                                   _TOTALS_RE)
    assert (len(ATTRIBUTIVE_TWINS), len(TOTALS_TWINS)) == (8, 2)
    # the matchers the forms were read with: explicit 0/8, attributive 8/8, one participle each
    assert sum(bool(_RECORDED_RE.search(r)) for r in ATTRIBUTIVE_TWINS) == 0
    assert [len(_RECORDED_ATTRIBUTIVE_RE.findall(r)) for r in ATTRIBUTIVE_TWINS] == [1] * 8
    assert sum("mensal registrada" in r for r in ATTRIBUTIVE_TWINS) == 4
    assert sum("meses registrados" in r for r in ATTRIBUTIVE_TWINS) == 4
    assert sum("líquido" in r for r in ATTRIBUTIVE_TWINS) == 4
    assert [bool(_TOTALS_RE.search(r)) for r in TOTALS_TWINS] == [True, True]
    assert not any(_RECORDED_ATTRIBUTIVE_RE.search(r) for r in TOTALS_TWINS)


@pytest.mark.parametrize("reply", [r for r in ATTRIBUTIVE_TWINS if "líquido" in r])
def test_BOTH_forms_in_one_reply_pass_only_because_both_rules_are_excused(reply):
    """The overlap: the participle AND «líquido» in the same reply, every figure in the read.
    Rule (1) fires first in the broken world; excusing it alone would hand the reply to rule (3)
    (SABOTAGE: drop `and not sourced` from rule (3) → these go red as `conjured_totals`)."""
    from cogno_praxis.bookkeeper.grounding import _TOTALS_RE
    assert _TOTALS_RE.search(reply)
    assert _main(reply) == "fabricated_entry"
    assert _rule(reply) is None


# ── the controls: what the read must NOT reach ───────────────────────────────────────────────
def test_the_old_corpus_shape_is_unchanged():
    """The earlier document (no participle, no totals word) passed then and passes now, on
    either side of the declaration — the turns measured before this defect appeared."""
    old_doc = ("## Aluguéis do imóvel\n- Loja: R$ 3.110,00 por mês\n- Sala: R$ 2.020,00 por mês\n"
               "- Apartamento: R$ 1.770,00 por mês\n")
    tools = [ToolCall(tool=DOC_READ, ok=True, result=old_doc)]
    reply = ("Pelo documento, os aluguéis do imóvel são: loja R$ 3.110,00, sala R$ 2.020,00 e "
             "apartamento R$ 1.770,00 por mês.")
    assert _main(reply, tools=tools) is None
    assert _rule(reply, tools=tools) is None
    assert _rule(reply, tools=tools, source_reads=()) is None


@pytest.mark.parametrize("reply", [
    "Registrado! R$ 150,00 da vistoria.",
    "Lançado: R$ 150,00 de vistoria!",
    "Lançada a vistoria de R$ 150,00.",
    "Pronto, registrada: R$ 150,00.",
    "✅ Registrado — R$ 150,00.",
])
def test_the_RECEIPT_shape_fires_even_when_the_document_holds_the_value(reply):
    """The document HOLDS R$ 150,00 (section 11), so the value condition alone would pass these.
    The participle OPENS its clause: nothing is being described, something is being receipted,
    and a document grounds a figure, never an act. The likeliest amount of a fabricated receipt
    is a price the business itself wrote down."""
    assert "R$ 150,00" in DOCUMENT
    assert _rule(reply) == "fabricated_entry"


@pytest.mark.parametrize("reply", [
    "Registrei R$ 150,00 da vistoria.",
    "Acabei de lançar a vistoria de R$ 150,00.",
    "A vistoria de R$ 150,00 foi registrada.",
    "Certo, já está lançado o valor de R$ 150,00.",
])
def test_the_EXPLICIT_claim_is_never_reached_by_a_source_read(reply):
    assert _rule(reply) == "fabricated_entry"


@pytest.mark.parametrize("reply,rule", [
    # loja + sala: a sum the document never wrote
    ("Loja e sala, registradas no documento, rendem juntas R$ 6.175,00.", "fabricated_entry"),
    ("O total da loja e da sala é R$ 6.175,00.", "conjured_totals"),
    # 12 × the monthly total: a year worked out from a month
    ("O total anual de aluguéis é R$ 90.720,00.", "conjured_totals"),
    ("Os aluguéis registrados rendem R$ 90.720,00 por ano.", "fabricated_entry"),
    # the net worked out to the cent (7.560 − 8%) where the document wrote R$ 6.955
    ("O líquido mensal é R$ 6.955,20.", "conjured_totals"),
    ("A receita mensal registrada rende líquido de R$ 6.955,20.", "fabricated_entry"),
])
def test_a_value_COMPUTED_from_the_document_is_still_caught(reply, rule):
    assert _rule(reply) == rule


@pytest.mark.parametrize("reply,rule", [
    ("As receitas registradas: loja R$ 3.715,00, sala R$ 2.460,00 e apartamento R$ 1.999,00.",
     "fabricated_entry"),
    ("O total mensal é R$ 7.560,00, com loja R$ 3.715,00 e sala R$ 2.999,00.",
     "conjured_totals"),
])
def test_ONE_value_the_document_does_not_hold_beside_two_it_does_is_still_caught(reply, rule):
    """EVERY value, not some: two figures from the document do not vouch for a third."""
    assert _rule(reply) == rule


def test_a_read_the_host_did_NOT_declare_grounds_nothing():
    """The name is the HOST's: the same read under a name nobody declared, and the same
    declared name with no call behind it, are the broken world."""
    reply = ATTRIBUTIVE_TWINS[0]
    other = [ToolCall(tool="consult_documents", ok=True, result=DOCUMENT)]
    assert _rule(reply, tools=other) == "fabricated_entry"                # not declared
    assert _rule(reply, tools=other, source_reads=()) == "fabricated_entry"
    assert _rule(reply, tools=other, source_reads={"consult_documents"}) is None
    assert _rule(reply, tools=()) == "fabricated_entry"                   # declared, not called


def test_any_name_the_host_declares_is_a_source_and_the_declaration_is_read_as_names():
    reply = TOTALS_TWINS[1]
    for decl in (DECLARED, [DOC_READ], (DOC_READ,), DOC_READ, {DOC_READ, "something_else"}):
        assert _rule(reply, source_reads=decl) is None, decl
    for junk in ((), [""], ["  "], [None], None, 7):
        assert _rule(reply, source_reads=junk) == "conjured_totals", junk


def test_a_FAILED_source_read_grounds_nothing():
    failed = [ToolCall(tool=DOC_READ, ok=False, result=DOCUMENT, error="timeout")]
    assert _rule(ATTRIBUTIVE_TWINS[0], tools=failed) == "fabricated_entry"
    assert _rule(TOTALS_TWINS[1], tools=failed) == "conjured_totals"


def test_a_ledger_write_CALLED_this_turn_takes_the_participle_exemption_away():
    """«registra a despesa do documento» → the write is refused → «receita registrada: R$ X»
    over a value the document holds. A write was attempted, so the participle is the claim of
    that write, and the read does not excuse it — the same FACT the stative exemption reads."""
    refused = [ToolCall(tool="add_outcome", ok=False, error="refused")]
    assert _rule(ATTRIBUTIVE_TWINS[0], tools=READ + refused) == "fabricated_entry"


def test_the_WHOLE_result_is_read_not_a_trace_excerpt():
    """The same read cut at 4000 characters — what a persisted trace keeps — holds none of the
    figures, and the reply is judged as before. The host hands the uncut output to this rule."""
    cut = [ToolCall(tool=DOC_READ, ok=True, result=DOCUMENT[:4000])]
    assert _rule(ATTRIBUTIVE_TWINS[0], tools=cut) == "fabricated_entry"
    assert _rule(TOTALS_TWINS[1], tools=cut) == "conjured_totals"


def test_known_limit_a_presentational_ESTAR_is_read_as_the_explicit_claim():
    """DECLARED LIMIT, outside this change by order: «Aqui estão os valores registrados» puts a
    form of ESTAR two words before the participle, which is the explicit branch's copula +
    participle — and the explicit branch is never excused by a read. A draft in that shape is
    still rewritten, on either side of the declaration; widening the explicit branch is its own
    decision, with its own measurement."""
    reply = ("Aqui estão os valores registrados no documento: loja R$ 3.715,00, sala "
             "R$ 2.460,00 e apartamento R$ 1.385,00.")
    assert _main(reply) == _rule(reply) == "fabricated_entry"


@pytest.mark.parametrize("reply", [
    "Tudo registrado: R$ 150,00 da vistoria.",
    "Vistoria registrada: R$ 150,00.",
    "R$ 150,00 registrado!",
])
def test_known_limit_a_receipt_with_a_word_before_the_participle_reads_as_the_listing(reply):
    """DECLARED LIMITS of the receipt shape (a word — or the value's own comma — before the
    participle): with a successful DECLARED read holding EVERY value and no ledger write called,
    these pass. It is the exposure a LEDGER read has today for ANY value, narrowed to values the
    document itself wrote; with nothing read, or the value absent, they fire as before."""
    assert _rule(reply) is None
    assert _main(reply) == "fabricated_entry"
    assert _rule(reply.replace("150,00", "151,00")) == "fabricated_entry"


def test_a_real_write_and_a_ledger_read_still_decide_as_before():
    wrote = [ToolCall(tool="add_income", ok=True, side_effect=True,
                      result="Income recorded: Aluguel = R$ 3.715,00 on 2026-10-05.")]
    assert _rule("Registrei a receita de R$ 3.715,00.", tools=READ + wrote) is None
    ledger = [ToolCall(tool="get_summary", ok=True, result="Income: R$ 3.715,00")]
    assert _rule("Registrado! R$ 150,00.", tools=ledger) is None   # the ledger read's own rule


# ── en / es: the same split ─────────────────────────────────────────────────────────────────
EN_DOC = "x" * 4100 + "\nRecorded rents: shop $3,715.00; office $2,460.00. Inspection fee: $150.00.\n"
ES_DOC = "x" * 4100 + "\nAlquileres registrados: local €3.715,00; oficina €2.460,00. Tasa: €150,00.\n"


@pytest.mark.parametrize("reply,doc,locale", [
    ("The recorded rents are $3,715.00 for the shop and $2,460.00 for the office.", EN_DOC, "en"),
    ("Los alquileres registrados son €3.715,00 (local) y €2.460,00 (oficina).", ES_DOC, "es"),
])
def test_en_es_the_listing_read_from_the_document_is_kept(reply, doc, locale):
    tools = [ToolCall(tool=DOC_READ, ok=True, result=doc)]
    assert _main(reply, tools=tools, locale=locale) == "fabricated_entry"
    assert _rule(reply, tools=tools, locale=locale) is None


@pytest.mark.parametrize("reply,doc,locale", [
    ("Recorded! $150.00 for the inspection.", EN_DOC, "en"),
    ("I've recorded the $150.00 inspection fee.", EN_DOC, "en"),
    ("¡Registrado! €150,00 de la tasa.", ES_DOC, "es"),
    ("Registré la tasa de €150,00.", ES_DOC, "es"),
])
def test_en_es_the_receipt_and_the_explicit_claim_still_fire(reply, doc, locale):
    tools = [ToolCall(tool=DOC_READ, ok=True, result=doc)]
    assert _rule(reply, tools=tools, locale=locale) == "fabricated_entry"


# ── the scheduler takes the same keyword and reads nothing from it ──────────────────────────
def test_the_scheduler_accepts_the_keyword_and_reads_nothing_from_it():
    for reply in ("Sua consulta está agendada para 05/10 às 11:00.",
                  "O horário de atendimento é das 08h às 18h."):
        a = sched_ground(reply, tools=READ, locale="pt")
        b = sched_ground(reply, tools=READ, locale="pt", source_reads=DECLARED)
        assert (a.rule if a else None) == (b.rule if b else None)


# ── no declaration → every verdict as before, byte for byte ─────────────────────────────────
# The corpus: every reply in this file (and the neighbouring shapes the rules already pin),
# against every kind of trace they meet, with and without declared values, on a read query and
# not. Its digest was taken on `origin/main` d81d3ca, BEFORE the parameter existed — a
# landing-time proof: regenerated only when a rule changes on purpose, and said so in the PR.
_DECL_VALUES = declared_values("Tarifa de vistoria: R$ 150,00. Aluguel da loja: R$ 3.715,00.")
_TRACES = {
    "none": [],
    "doc": READ,
    "doc_other_name": [ToolCall(tool="consult_documents", ok=True, result=DOCUMENT)],
    "doc_failed": [ToolCall(tool=DOC_READ, ok=False, error="timeout")],
    "ledger": [ToolCall(tool="get_summary", ok=True, result="Income: R$ 3.715,00")],
    "write_ok": [ToolCall(tool="add_income", ok=True, side_effect=True,
                          result="Income recorded: Aluguel = R$ 3.715,00 on 2026-10-05.")],
    "write_refused": [ToolCall(tool="add_outcome", ok=False, error="refused")],
}
_CORPUS_PT = ATTRIBUTIVE_TWINS + TOTALS_TWINS + [
    "Registrado! R$ 150,00 da vistoria.", "Lançado: R$ 150,00 de vistoria!",
    "Registrei R$ 150,00 da vistoria.", "A vistoria de R$ 150,00 foi registrada.",
    "Loja e sala, registradas no documento, rendem juntas R$ 6.175,00.",
    "O total da loja e da sala é R$ 6.175,00.", "O total anual de aluguéis é R$ 90.720,00.",
    "As receitas registradas: loja R$ 3.715,00, sala R$ 2.460,00 e apartamento R$ 1.999,00.",
    "O líquido mensal é R$ 6.955,20.", "A receita mensal registrada rende líquido de R$ 6.955,20.",
    "Tudo registrado: R$ 150,00 da vistoria.", "Vistoria registrada: R$ 150,00.",
    "R$ 150,00 registrado!",
    "Aqui estão os valores registrados no documento: loja R$ 3.715,00, sala R$ 2.460,00.",
    "Tenho registrado o seguinte: R$ 150,00 de vistoria.",
    "Removi a despesa de R$ 150,00.", "Não há lançamentos registrados.",
    "Tudo certo por aqui.",
]
_CORPUS_OTHER = [
    ("The recorded rents are $3,715.00 for the shop and $2,460.00 for the office.", "en"),
    ("Recorded! $150.00 for the inspection.", "en"),
    ("Los alquileres registrados son €3.715,00 (local) y €2.460,00 (oficina).", "es"),
    ("¡Registrado! €150,00 de la tasa.", "es"),
]
DIGEST_AT_MAIN = "f7b551127c422aa4f39cbc08b2cd7437decd95972556164ae9af539e4445139d"


def _verdicts(**kw):
    out = []
    cases = [(r, "pt") for r in _CORPUS_PT] + _CORPUS_OTHER
    for reply, locale in cases:
        for name, tools in sorted(_TRACES.items()):
            for decl in ((), _DECL_VALUES):
                for read in (False, True):
                    v = ground_reply(reply, tools=list(tools), locale=locale, is_read_query=read,
                                     declared_values=decl, **kw)
                    out.append([reply, locale, name, bool(decl), read,
                                None if v is None else [v.rule, v.message, v.repairable,
                                                        v.critique]])
    return out


def _digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest()


def test_no_declaration_is_the_verdict_of_main_byte_for_byte():
    """SABOTAGE: let an empty declaration admit any read (or a read by a name written here) →
    this digest moves. The broken-world half of every twin above is this same call."""
    assert _digest(_verdicts()) == DIGEST_AT_MAIN
    assert _digest(_verdicts(source_reads=())) == DIGEST_AT_MAIN
    assert _digest(_verdicts(source_reads=[])) == DIGEST_AT_MAIN
