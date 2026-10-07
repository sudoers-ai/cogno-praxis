"""Templated e-mail fields — the CLOSED list of markers, and the pure code that fills them.

A tenant writes an e-mail template (a subject and a body) for a persona, with markers such as
``[nome]``, ``[aulas]`` or ``[valores_por_bonus]``. When somebody asks for that e-mail to be sent,
the host resolves the recipient and the month, and this module fills every marker **in code**.
The model writes exactly one of them, ``[conteudo]`` — the free text from the request — and nothing
else: a figure, a date or an address copied by a model is the copy that goes wrong.

**One definition, many consumers.** :data:`EMAIL_FIELDS` is the list. The template validator, the
fill, the render, the host's tool description and the admin UI's help all read it; nobody keeps a
second copy. A marker outside it is REFUSED when the template is saved
(:func:`validate_template`), and so is any ``[`` that does not open a known marker — that is what
catches a typo like ``[nmoe]`` before it ships as literal text to a professor.

**The list has two halves, and a template belongs to a PERSONA (E3).** :data:`GENERIC_FIELDS`
are the markers ANY persona's template may use: their values come from the tenant's records, the
tenant itself, the request or the clock — ``[nome]``, ``[email]``, ``[empresa]``, ``[mes]``,
``[data]``, ``[assinatura]``, ``[solicitante]``, ``[conteudo]``. Everything else is SPECIFIC to
one persona and is declared by that persona's :class:`FieldProvider` in :data:`FIELD_PROVIDERS`:
today only the coordinator's (``[aulas]``, ``[disciplinas]``, ``[valor_por_aula]``,
``[valores_por_bonus]``, ``[total]``). :data:`EMAIL_FIELDS` is the union, derived — never typed.
So :func:`validate_template` takes the persona the template is being saved FOR, and a marker
another persona supplies is refused there by name, with the persona that does supply it: a
front-desk template that says ``[aulas]`` would otherwise save and then ask the requester, at
every send, for classes no front desk reads.

A provider DECLARES fields; it does not read them. Which service answers for a provider's
fields is the host's wiring (:func:`provider_fields` tells it which providers a template needs,
and a template of generic markers alone needs none). This module imports no service.

**A field with no value STOPS the send.** :func:`fill_email_fields` returns ``(values, missing)``
and never raises; each :class:`Missing` names the field, where it should have come from and why
it is not there, in the vertical's own words. The host turns a non-empty ``missing`` into a
QUESTION to the requester instead of a proposal. :func:`render_email` refuses to run with a
marker that has no value — it is never reached with one.

What deliberately is NOT here, by the owner's decisions of 2026-10-06:

* ``[cpf_cnpj]`` — removed: no personal data beyond the recipient's own name and address;
* ``[contrato]`` — the attachment arrives in phase E3; a template using it is refused until then;
* the recipient's ADDRESS is never free text: it is the identity's own e-mail, from the tenant's
  records, and an empty one stops the send even when the body never says ``[email]``;
* a marker for the SENDER's mailbox: ``[assinatura]`` is the display name of the persona that
  sends and ``[solicitante]`` the name of the person who asked. Neither is the From of the
  tenant's mailbox, and no marker quotes a third person's data.

Pure, deterministic, no I/O. The strings a person reads are Brazilian Portuguese, like the pay
block they sit beside (:mod:`cogno_praxis.coordinator.pay`).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Iterable, Mapping, Optional, Sequence

from cogno_praxis.coordinator.pay import PayEstimate, _condition_lines, fmt_money

# ── the closed list ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FieldSpec:
    """One marker: its name, where its value comes from, and whether it spans lines."""
    name: str
    source: str
    multiline: bool = False


@dataclass(frozen=True)
class FieldProvider:
    """The markers ONE persona supplies beyond the generic ones — a DECLARATION, not a reader.

    ``persona`` is the persona's id as the host names it; ``name`` is the vertical whose read
    the values come from (the host keys its resolver by it); ``label`` is how a refusal names
    that vertical to a person. ``needs_month`` — every field here is a figure about ONE month,
    so a template using any of them cannot be sent without one (:func:`template_needs_month`).
    """
    persona: str
    name: str
    label: str
    fields: "tuple[FieldSpec, ...]"
    needs_month: bool = False

    @property
    def field_names(self) -> "frozenset[str]":
        return frozenset(f.name for f in self.fields)


#: Markers a template may NOT use, with the sentence the refusal says. Known names, so the
#: refusal can say WHY rather than "unknown marker". Refused for EVERY persona.
REFUSED_FIELDS: "Mapping[str, str]" = MappingProxyType({
    "cpf_cnpj": "[cpf_cnpj] foi removido por decisão do dono: nenhum dado pessoal além do nome e "
                "do e-mail do próprio destinatário",
    "contrato": "[contrato] fica disponível na fase E3 (o anexo do contrato)",
})

#: The markers ANY persona's template may use. Each value comes from something every turn has:
#: the recipient's record, the tenant, the request, the clock, the persona that sends and the
#: person who asked. None of them needs a persona's own read.
GENERIC_FIELDS: "Mapping[str, FieldSpec]" = MappingProxyType({f.name: f for f in (
    FieldSpec("nome", "o nome do destinatário no cadastro"),
    FieldSpec("email", "o e-mail do destinatário no cadastro"),
    FieldSpec("empresa", "o nome do tenant"),
    FieldSpec("mes", "o mês do pedido (AAAA-MM)"),
    FieldSpec("data", "a data de hoje, no fuso do tenant"),
    FieldSpec("assinatura", "o nome de exibição da persona que envia"),
    FieldSpec("solicitante", "o nome de quem pediu o envio, no cadastro"),
    FieldSpec("conteudo", "o texto do pedido", multiline=True),
)})


def _registry(generic: "Mapping[str, FieldSpec]", providers: "Iterable[FieldProvider]"
              ) -> "tuple[Mapping[str, FieldProvider], Mapping[str, FieldSpec]]":
    """``(providers by persona, every field by name)`` — or ``ValueError`` for a registry that
    could answer two ways: a persona declared twice, or a marker that is already a generic one,
    a refused one or another provider's. A dict built without this check keeps the LAST one in
    silence, and the validator would then say one thing and the fill another."""
    by_persona: "dict[str, FieldProvider]" = {}
    fields: "dict[str, FieldSpec]" = dict(generic)
    for p in providers:
        if not p.persona or p.persona != p.persona.strip() or p.persona in by_persona:
            raise ValueError(f"field provider persona {p.persona!r} is blank or declared twice")
        for f in p.fields:
            if f.name in fields or f.name in REFUSED_FIELDS:
                raise ValueError(f"[{f.name}] of {p.persona} is already a marker")
            fields[f.name] = f
        by_persona[p.persona] = p
    return MappingProxyType(by_persona), MappingProxyType(fields)


#: The persona-specific markers, by the persona that supplies them. A persona absent from here
#: has the generic ones and nothing else.
FIELD_PROVIDERS: "Mapping[str, FieldProvider]"
#: EVERY marker that exists — the generic ones, then each provider's. Derived.
EMAIL_FIELDS: "Mapping[str, FieldSpec]"
FIELD_PROVIDERS, EMAIL_FIELDS = _registry(GENERIC_FIELDS, (
    FieldProvider(persona="COORDINATOR", name="coordinator", label="coordenação",
                  needs_month=True, fields=(
        FieldSpec("disciplinas", "as aulas do mês na agenda da coordenação", multiline=True),
        FieldSpec("aulas", "as aulas do mês na agenda da coordenação", multiline=True),
        FieldSpec("valor_por_aula", "as regras da persona (HOURS_PER_CLASS × PAY_RATE_PER_HOUR)"),
        FieldSpec("valores_por_bonus", "as regras da persona (IBOPE_BONUS) e as aulas do mês",
                  multiline=True),
        FieldSpec("total", "o resultado do IBOPE e as regras da persona"),
    )),
))

#: The phase a REFUSED field becomes available in. ``cpf_cnpj`` has none: it is not coming back.
_FIELD_PHASE: "Mapping[str, str]" = MappingProxyType({"contrato": "E3"})
_PHASES = ("E1", "E2", "E3")

#: Markers that may not appear in the SUBJECT: multi-line values, or free text the model writes.
SUBJECT_FORBIDDEN: "frozenset[str]" = frozenset({"conteudo", "aulas", "disciplinas",
                                                 "valores_por_bonus"})

#: Ceilings. The body's is the template's (what the tenant wrote); the free text's is the model's.
MAX_BODY_CHARS = 10_000
MAX_CONTEUDO_CHARS = 1_000

_MARKER = re.compile(r"\[([a-z_]+)\]")
_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_PT_MONTHS = ("", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
              "setembro", "outubro", "novembro", "dezembro")


def provider_for(persona: "Optional[str]") -> "Optional[FieldProvider]":
    """The provider of ``persona``, or ``None`` — the persona has the generic markers only.

    The id is compared AS WRITTEN (surrounding blanks aside): it is an identifier, not prose, and
    a persona that merely resembles another one does not inherit its markers."""
    return FIELD_PROVIDERS.get(persona.strip()) if isinstance(persona, str) else None


def provider_of(field: str) -> "Optional[FieldProvider]":
    """The provider that supplies ``field``, or ``None`` for a generic (or unknown) marker."""
    for p in FIELD_PROVIDERS.values():
        if field in p.field_names:
            return p
    return None


def fields_for(persona: "Optional[str]") -> "Mapping[str, FieldSpec]":
    """The markers a template of ``persona`` may use: the generic ones and its provider's.

    ``None`` — the caller does not say whose template it is — answers EVERY marker, the reading
    from before templates belonged to a persona. It is kept for a caller that has no persona to
    give (a doc check, a pre-E3 host); a caller that knows the persona passes it, and any string,
    the empty one included, is a persona."""
    if persona is None:
        return EMAIL_FIELDS
    p = provider_for(persona)
    if p is None:
        return GENERIC_FIELDS
    return MappingProxyType({**GENERIC_FIELDS, **{f.name: f for f in p.fields}})


def known_markers(persona: "Optional[str]" = None) -> "tuple[str, ...]":
    """``("[nome]", "[email]", …)`` — the list as a person reads it: :func:`fields_for` this
    persona, generic markers first."""
    return tuple(f"[{n}]" for n in fields_for(persona))


def provider_fields(fields: "Iterable[str]") -> "dict[str, tuple[str, ...]]":
    """``{provider name: its fields among these}`` — which persona reads a template needs.

    Empty for a template of generic markers alone: nothing persona-specific has to be read to
    compose it, and the host then asks no provider at all."""
    out: "dict[str, list[str]]" = {}
    for name in dict.fromkeys(fields):
        p = provider_of(name)
        if p is not None:
            out.setdefault(p.name, []).append(name)
    return {k: tuple(v) for k, v in out.items()}


def template_needs_month(fields: "Iterable[str]") -> bool:
    """Whether a template using ``fields`` cannot be composed without the month of the request:
    it says ``[mes]``, or it uses a field of a provider whose figures are about one month. A
    template that needs none must never make anybody invent one."""
    names = set(fields)
    return "mes" in names or any(p.needs_month and names & p.field_names
                                 for p in FIELD_PROVIDERS.values())


def markers_cited(text: str) -> "tuple[str, ...]":
    """Every ``[lowercase_name]`` written in ``text``, in order, de-duplicated — for a test that
    checks a doc, a prompt or a UI cites no marker outside :data:`EMAIL_FIELDS`."""
    seen: list[str] = []
    for m in _MARKER.finditer(text or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return tuple(seen)


# ── the template ─────────────────────────────────────────────────────────────────────────────

def template_fields(subject: str, body: str) -> "tuple[str, ...]":
    """The markers a template uses, subject first, in order of first appearance."""
    return tuple(dict.fromkeys(markers_cited(subject or "") + markers_cited(body or "")))


def _bracket_problems(text: str, where: str, phase: str,
                      persona: "Optional[str]" = None) -> "list[str]":
    """Every ``[`` in ``text`` that does not open a marker THIS persona has — named, with its
    position, and a marker of another persona with the persona that supplies it."""
    out: list[str] = []
    usable = fields_for(persona)
    allowed = ", ".join(known_markers(persona))
    whose = str(persona).strip() if persona is not None else ""
    for i, ch in enumerate(text):
        if ch != "[":
            continue
        m = _MARKER.match(text, i)
        if m is None:
            snippet = text[i:i + 15].split("\n", 1)[0]
            out.append(f"no {where}, «{snippet}» (posição {i + 1}) abre um «[» que não é "
                       f"marcador; os marcadores são {allowed}")
            continue
        name = m.group(1)
        if name in usable:
            continue
        if name in REFUSED_FIELDS:
            since = _FIELD_PHASE.get(name)
            if since is not None and _PHASES.index(phase) >= _PHASES.index(since):
                continue
            out.append(f"no {where}: {REFUSED_FIELDS[name]}")
            continue
        owner = provider_of(name)
        if owner is not None:
            # A real marker, of ANOTHER persona: say whose it is and who is asking for it.
            out.append(f"no {where}, [{name}] é um marcador da persona {owner.persona} "
                       f"({owner.label}); {f'a persona {whose}' if whose else 'esta persona'} "
                       f"não o tem — os marcadores desta persona são {allowed}")
            continue
        out.append(f"no {where}, [{name}] não é um marcador; os marcadores são {allowed}")
    return out


def validate_template(subject: str, body: str, *, phase: str = "E1",
                      persona: "Optional[str]" = None) -> "tuple[str, ...]":
    """Every reason this template cannot be saved, in words — ``()`` when it is valid.

    Never raises. Each reason is a sentence the tenant's admin reads (the host answers 400 with
    the list), so it names what is wrong and where, and lists the markers that DO exist.

    ``persona`` — the persona the template is saved for. Its markers are the generic ones and its
    own provider's (:func:`fields_for`); a marker another persona supplies is refused with both
    personas named. ``None`` validates against every marker, as before templates had a persona.
    """
    if phase not in _PHASES:
        raise ValueError(f"phase must be one of {_PHASES}, not {phase!r}")
    subject = subject if isinstance(subject, str) else ""
    body = body if isinstance(body, str) else ""
    out: list[str] = []
    if not subject.strip():
        out.append("o assunto está vazio")
    elif "\n" in subject or "\r" in subject:
        out.append("o assunto tem de ser uma linha só")
    if not body.strip():
        out.append("o corpo está vazio")
    elif len(body) > MAX_BODY_CHARS:
        out.append(f"o corpo tem {len(body)} caracteres; o máximo é {MAX_BODY_CHARS}")
    out += _bracket_problems(subject, "assunto", phase, persona)
    out += _bracket_problems(body, "corpo", phase, persona)
    for name in markers_cited(subject):
        if name in SUBJECT_FORBIDDEN:
            out.append(f"[{name}] não pode ir no assunto (tem várias linhas ou é texto livre)")
    uses = len([m for m in _MARKER.finditer(subject + "\n" + body) if m.group(1) == "conteudo"])
    if uses > 1:
        out.append(f"[conteudo] aparece {uses} vezes; só pode aparecer uma")
    return tuple(out)


# ── the context it is filled from ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EmailClass:
    """One PAYABLE class of the month: the date, the hour (``""`` when the sheet has none — never
    a guessed one), the discipline and the class group (the spreadsheet's own label)."""
    when: date
    time: str
    subject: str
    turma: str


@dataclass(frozen=True)
class EmailContext:
    """Everything a template is filled from. The coordinator's half comes from ONE read
    (``CoordinatorService.email_context``); the recipient, the tenant, the clock (``today``, in
    the tenant's zone), the persona that sends (``persona_name``) and the person who asked
    (``requester_name``) come from the host. A generic marker is filled from the host's half
    alone, so a context no persona read anything into still composes a generic template.

    ``schedule_error`` — the schedule could not be read for this person (access refused, a sheet
    that failed): every schedule-derived field is missing, with this sentence. ``pay_error`` —
    the rules do not declare the pay: the pay fields are missing, with this sentence. Both are the
    vertical's own words and are never wrapped in another.
    """
    recipient_name: str = ""
    recipient_email: str = ""
    tenant_name: str = ""
    month: str = ""
    conteudo: str = ""
    professor: str = ""
    classes: "tuple[EmailClass, ...]" = ()
    estimate: Optional[PayEstimate] = None
    schedule_error: str = ""
    pay_error: str = ""
    today: Optional[date] = None
    persona_name: str = ""
    requester_name: str = ""


@dataclass(frozen=True)
class Missing:
    """A field the send cannot fill: which one, where it comes from, and why it is not there."""
    field: str
    source: str
    reason: str

    def sentence(self) -> str:
        return f"[{self.field}] — {self.reason} (fonte: {self.source})"


def is_email_month(raw: str) -> bool:
    """``YYYY-MM`` with a real month — the only period an e-mail is about."""
    return bool(_MONTH.match((raw or "").strip()))


def month_words(raw: str) -> str:
    """``"2026-10"`` → ``"outubro/2026"``; ``""`` for anything else."""
    m = _MONTH.match((raw or "").strip())
    return f"{_PT_MONTHS[int(m.group(2))]}/{m.group(1)}" if m else ""


def _month_numeric(raw: str) -> str:
    m = _MONTH.match((raw or "").strip())
    return f"{m.group(2)}/{m.group(1)}" if m else (raw or "")


def date_words(day: date) -> str:
    """``date(2026, 10, 7)`` → «7 de outubro de 2026»; the first of a month is «1º de …», as a
    Brazilian letter writes it. ``[data]``'s value."""
    return f"{'1º' if day.day == 1 else day.day} de {_PT_MONTHS[day.month]} de {day.year}"


#: The fields the coordinator's schedule read produces (its provider's, derived), and the ones
#: that need the pay rules.
_SCHEDULE_FIELDS = FIELD_PROVIDERS["COORDINATOR"].field_names
_PAY_FIELDS = frozenset({"valor_por_aula", "valores_por_bonus", "total"})
#: The fields that are a figure about the MONTH'S classes — meaningless with none.
_NEEDS_CLASSES = frozenset({"disciplinas", "aulas", "valores_por_bonus", "total"})


def _line_of(c: EmailClass) -> str:
    stamp = c.when.strftime("%d/%m") + (f" {c.time}" if c.time else "")
    return f"{stamp} — {c.subject} — {c.turma}"


def _bonus_value(est: PayEstimate) -> str:
    """``[valores_por_bonus]``: «Sem bônus» and one line per DECLARED band, always — the levels
    the rules declare, not the hypotheses (which are empty once the result was read). The
    applied band is marked only when the bonus is DETERMINED; with ``not_found``/``gap`` no line
    is marked and none is chosen."""
    base, hours, state = est.base, est.hours, est.bonus_state
    pct = f"{est.ibope_pct:g}" if est.ibope_pct is not None else ""
    applied = est.matched_tier if state == "applied" else None
    mark = f" ← apurado (IBOPE {pct}%)"
    lines = [f"Sem bônus: {fmt_money(base)}" + (mark if state == "below" else "")]
    for t in est.tiers:
        lines.append(f"{t.label}: {fmt_money(base + hours * t.per_hour)}"
                     + (mark if applied is not None and t == applied else ""))
    cond = [ln for ln in _condition_lines(est) if ln]
    return "\n".join(lines + ([""] + cond if cond else []))


def fill_email_fields(fields: "Iterable[str]", context: EmailContext
                      ) -> "tuple[dict[str, str], tuple[Missing, ...]]":
    """Fill ``fields`` (a template's markers) from ``context`` — ``(values, missing)``.

    Never raises. ``missing`` is empty exactly when every requested field has a value AND the
    recipient has an address — ``[email]`` is checked always, because it is where the e-mail
    goes, whether or not the body quotes it. A free text given to a template with no
    ``[conteudo]`` is also a ``Missing``: it would be dropped in silence, and the requester asked
    for it to be said.
    """
    wanted = tuple(dict.fromkeys(f for f in fields if f in EMAIL_FIELDS))
    values: dict[str, str] = {}
    missing: list[Missing] = []

    def miss(name: str, reason: str) -> None:
        missing.append(Missing(name, EMAIL_FIELDS[name].source, reason))

    who = context.recipient_name.strip() or context.professor.strip() or "o destinatário"
    month_num = _month_numeric(context.month)
    if not context.recipient_email.strip():
        miss("email", f"{who} não tem e-mail no cadastro")
    for name in wanted:
        if name == "nome":
            if context.recipient_name.strip():
                values[name] = context.recipient_name.strip()
            else:
                miss(name, "o destinatário não tem nome no cadastro")
        elif name == "email":
            if context.recipient_email.strip():
                values[name] = context.recipient_email.strip()
        elif name == "empresa":
            if context.tenant_name.strip():
                values[name] = context.tenant_name.strip()
            else:
                miss(name, "o tenant não tem nome")
        elif name == "mes":
            if is_email_month(context.month):
                values[name] = month_words(context.month)
            else:
                miss(name, f"o mês «{context.month}» não é AAAA-MM" if context.month.strip()
                     else "o pedido não diz de que mês é")
        elif name == "data":
            if isinstance(context.today, date):
                values[name] = date_words(context.today)
            else:
                miss(name, "o sistema não informou a data de hoje")
        elif name == "assinatura":
            if context.persona_name.strip():
                values[name] = context.persona_name.strip()
            else:
                miss(name, "a persona que envia não tem nome de exibição")
        elif name == "solicitante":
            if context.requester_name.strip():
                values[name] = context.requester_name.strip()
            else:
                miss(name, "quem pediu o envio não tem nome no cadastro")
        elif name == "conteudo":
            text = context.conteudo.strip()
            if not text:
                miss(name, "o template tem [conteudo] e o pedido não trouxe o texto")
            elif len(text) > MAX_CONTEUDO_CHARS:
                miss(name, f"o texto tem {len(text)} caracteres; o máximo é {MAX_CONTEUDO_CHARS}")
            else:
                values[name] = text
        elif name in _SCHEDULE_FIELDS:
            _fill_schedule_field(name, context, who, month_num, values, miss)
    if "conteudo" not in wanted and context.conteudo.strip():
        miss("conteudo", "este template não tem espaço para texto livre")
    return values, tuple(missing)


def _fill_schedule_field(name, context, who, month_num, values, miss) -> None:
    if not is_email_month(context.month):
        miss(name, "sem um mês AAAA-MM não há aulas a ler")
        return
    if context.schedule_error:
        miss(name, context.schedule_error)
        return
    if name in _NEEDS_CLASSES and not context.classes:
        miss(name, f"não encontro aulas de {who} em {month_num} na agenda; confirma o mês?")
        return
    if name in _PAY_FIELDS and (context.pay_error or context.estimate is None):
        miss(name, context.pay_error or "a estimativa de remuneração não foi lida")
        return
    est = context.estimate
    if name == "aulas":
        ordered = sorted(context.classes, key=lambda c: (c.when, c.time or "99:99"))
        values[name] = "\n".join(_line_of(c) for c in ordered)
    elif name == "disciplinas":
        subjects = {c.subject for c in context.classes}
        values[name] = "\n".join(sorted(subjects, key=lambda s: (s.casefold(), s)))
    elif name == "valor_por_aula" and est is not None:
        values[name] = fmt_money(est.hours_per_class * est.rate)
    elif name == "valores_por_bonus" and est is not None:
        if not est.tiers:
            miss(name, "as regras não declaram faixas de bônus (IBOPE_BONUS)")
        else:
            values[name] = _bonus_value(est)
    elif name == "total" and est is not None:
        state = est.bonus_state
        if not est.tiers:
            values[name] = fmt_money(est.base)          # no bonus scheme: the base IS the total
        elif state == "applied" and est.matched_tier is not None:
            values[name] = fmt_money(est.base + est.hours * est.matched_tier.per_hour)
        elif state == "below":
            values[name] = fmt_money(est.base)
        else:
            miss(name, "o bônus ainda não está apurado; use [valores_por_bonus]")


# ── the render ───────────────────────────────────────────────────────────────────────────────

def render_email(subject: str, body: str, values: "Mapping[str, str]") -> "tuple[str, str]":
    """Substitute every marker by its value — ONE pass, so a value is never read as a template
    (a ``[total]`` typed inside the free text stays those seven characters).

    Raises ``ValueError`` for a marker with no value: the caller is never supposed to get here
    with a ``missing`` — this is the floor under that rule, not a path.
    """
    def sub(text: str) -> str:
        def repl(m: "re.Match[str]") -> str:
            name = m.group(1)
            if name not in values:
                raise ValueError(f"[{name}] has no value — fill_email_fields reported it missing")
            return values[name]
        return _MARKER.sub(repl, text)

    out_subject = sub(subject)
    if "\n" in out_subject or "\r" in out_subject:
        raise ValueError("the rendered subject spans more than one line")
    return out_subject.strip(), sub(body)


def email_digest(subject: str, body: str) -> str:
    """The digest a proposal records and a confirmation compares: SHA-256 of
    ``subject + "\\n" + body``, hex. One definition, so the two sides cannot hash differently."""
    return hashlib.sha256((subject + "\n" + body).encode("utf-8")).hexdigest()


def missing_question(missing: "Sequence[Missing]") -> str:
    """The question a non-empty ``missing`` turns into — each field named, with its source."""
    lines = [m.sentence() for m in missing]
    return ("Não consigo montar este e-mail sem o que falta:\n" + "\n".join(f"- {ln}" for ln in lines))


__all__ = [
    "EMAIL_FIELDS", "GENERIC_FIELDS", "FIELD_PROVIDERS", "FieldSpec", "FieldProvider",
    "REFUSED_FIELDS", "SUBJECT_FORBIDDEN", "MAX_BODY_CHARS",
    "MAX_CONTEUDO_CHARS", "EmailClass", "EmailContext", "Missing", "known_markers",
    "fields_for", "provider_for", "provider_of", "provider_fields", "template_needs_month",
    "markers_cited", "template_fields", "validate_template", "fill_email_fields",
    "render_email", "email_digest", "missing_question", "is_email_month", "month_words",
    "date_words",
]
