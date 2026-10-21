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

**ONE list for every persona; who can FILL each marker is a separate question (2026-10-21).**
The owner's rule: the markers are standard for everything, not specific to a persona. So
:func:`validate_template` accepts every marker of :data:`EMAIL_FIELDS` in any persona's
template — it answers «which markers EXIST», and that answer is the same for everyone.
:data:`FIELD_PROVIDERS` still answers the other question, «who has somewhere to READ this
marker from». :data:`GENERIC_FIELDS` are filled from what every turn has (the tenant's records,
the tenant itself, the request, the clock): ``[nome]``, ``[email]``, ``[empresa]``, ``[mes]``,
``[data]``, ``[assinatura]``, ``[solicitante]``, ``[conteudo]``. Everything else is read by ONE
persona and is declared by that persona's :class:`FieldProvider`: today only the coordinator's
(``[aulas]``, ``[disciplinas]``, ``[valor_por_aula]``, ``[valores_por_bonus]``, ``[total]``).
:data:`EMAIL_FIELDS` is the union, derived — never typed. :func:`fields_for` says what one
persona can fill. A template that uses a marker its persona cannot fill SAVES; at the send,
``fill_email_fields(…, persona=…)`` returns that marker as a :class:`Missing` naming it and who
reads it («o template usa [aulas], que esta persona não consegue preencher: só a coordenação
(COORDINATOR) o lê»), and the send asks the requester instead of sending. Until 2026-10-21 such a
template was refused at save, by persona (E3, 2026-10-07).

A provider DECLARES fields; it does not read them. Which service answers for a provider's
fields is the host's wiring (:func:`provider_fields` tells it which providers a template needs,
and a template of generic markers alone needs none). This module imports no service.

**The tenant's own markers — company tags with a FIXED value (2026-10-21).** Beside the
thirteen, a tenant may declare tags of its own: ``{name: value}``, valid in EVERY persona's
template (the owner's rule: the tags are standard for everything). The name is
:data:`CUSTOM_TAG_NAME` (``[a-z][a-z0-9_]{1,30}``) and is never a marker of
:data:`EMAIL_FIELDS` nor a name of :data:`REFUSED_FIELDS`; the value is plain text, one line or
several, at most :data:`MAX_CUSTOM_TAG_CHARS` characters — the business's DATA, never an
instruction. :func:`normalise_custom_tags` is the SAVE door (every refusal named) and
:func:`parse_custom_tags` the TURN's (tolerant: it drops what the save would refuse). The value
is filled deterministically by :func:`fill_email_fields`, from ``EmailContext.custom_tags``,
before any provider and in any persona: a value is the tenant's, not a persona's read.
:func:`validate_template` accepts the tenant's tag names (``custom_tags=``); a template whose tag
was removed after it was saved is refused by the save and kept by the turn
(``any_company_tag=True``), and the fill returns it as a :class:`Missing` —
«tag personalizada removida» — so the send asks the requester instead of sending. Tags filled by
data (a provider, code), tags of one persona only and HTML are not here.

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
from dataclasses import dataclass, field
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

#: A marker: ``[`` + a lowercase name + ``]``. A strict superset of the grammar before company
#: tags (``[a-z_]+``): the first character is the same, and digits may follow it, because a
#: company tag's name may carry them (``[sala2]``). A bracketed number (``[2026]``) still opens no
#: marker.
_MARKER = re.compile(r"\[([a-z_][a-z0-9_]*)\]")
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
    """The markers ``persona`` can FILL: the generic ones and its own provider's.

    This is not what a template may USE — every marker of :data:`EMAIL_FIELDS` is valid in any
    persona's template (:func:`validate_template`). It is what this persona has somewhere to read
    from; a host composing an e-mail asks it, and a marker outside it comes out as ``missing``.

    ``None`` — the caller does not say whose it is — answers EVERY marker. Any string, the empty
    one included, is a persona."""
    if persona is None:
        return EMAIL_FIELDS
    p = provider_for(persona)
    if p is None:
        return GENERIC_FIELDS
    return MappingProxyType({**GENERIC_FIELDS, **{f.name: f for f in p.fields}})


def known_markers(persona: "Optional[str]" = None) -> "tuple[str, ...]":
    """``("[nome]", "[email]", …)`` — the list as a person reads it, generic markers first. With
    no ``persona``, every marker (the ONE list a template may use); with one, the markers that
    persona can fill (:func:`fields_for`)."""
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


# ── the tenant's own markers: company tags with a FIXED value ─────────────────────────────────

#: A company tag's NAME: a lowercase letter, then 1 to 30 lowercase letters, digits or ``_``.
#: No accent, no space, no capital: it is an identifier the tenant types into a template.
CUSTOM_TAG_NAME = re.compile(r"[a-z][a-z0-9_]{1,30}")
#: The longest VALUE a company tag may hold, counted after it is normalised.
MAX_CUSTOM_TAG_CHARS = 500
#: How many tags one tenant may declare. A runaway guard, not a product limit.
MAX_CUSTOM_TAGS = 50
#: Where a company tag's value comes from — the ``source`` of its :class:`Missing`.
CUSTOM_TAG_SOURCE = "as tags personalizadas da empresa"
#: The reason a template's company tag has no value: the tenant removed it after the template
#: was saved (a name the save door did not know is never saved, so an unknown one IS removed).
CUSTOM_TAG_REMOVED = "tag personalizada removida"
#: Control characters a plain-text value may carry: the line break and the tab.
_ALLOWED_CONTROLS = frozenset("\n\t")


def is_custom_tag_name(name: object) -> bool:
    """Whether ``name`` can be a company tag: the grammar, and not a standard or reserved name.

    A name that collides is never a tag, wherever it is handed over — so a tag can neither
    unlock a reserved marker nor override a standard one."""
    return (isinstance(name, str) and CUSTOM_TAG_NAME.fullmatch(name) is not None
            and name not in EMAIL_FIELDS and name not in REFUSED_FIELDS)


def _custom_value(value: str) -> str:
    """The value as it is stored and filled: line endings as ``\\n``, outer blanks off."""
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def custom_tag_problems(name: object, value: object) -> "tuple[str, ...]":
    """Every reason the company tag ``name`` → ``value`` cannot be saved, in words — ``()`` when
    it can. Never raises. Each sentence names the tag, so a list of them needs no index."""
    if not isinstance(name, str) or CUSTOM_TAG_NAME.fullmatch(name) is None:
        shown = name[:40] if isinstance(name, str) else type(name).__name__
        return (f"«{shown}» não serve como nome de tag: só letras minúsculas sem acento, "
                "algarismos e «_», a começar por uma letra, de 2 a 31 caracteres",)
    if name in EMAIL_FIELDS:
        return (f"[{name}] já é um marcador padrão ({EMAIL_FIELDS[name].source}); "
                "escolha outro nome",)
    if name in REFUSED_FIELDS:
        return (f"[{name}] é um nome reservado: {REFUSED_FIELDS[name]}",)
    if not isinstance(value, str):
        return (f"o valor de [{name}] tem de ser texto",)
    text = _custom_value(value)
    if any((ord(c) < 32 or ord(c) == 127) and c not in _ALLOWED_CONTROLS for c in text):
        return (f"o valor de [{name}] tem um caractere de controle; só texto simples "
                "(com quebras de linha e tabulações)",)
    if not text:
        return (f"o valor de [{name}] está vazio",)
    if len(text) > MAX_CUSTOM_TAG_CHARS:
        return (f"o valor de [{name}] tem {len(text)} caracteres; o máximo é "
                f"{MAX_CUSTOM_TAG_CHARS}",)
    return ()


def normalise_custom_tags(raw: object) -> "tuple[dict[str, str], tuple[str, ...]]":
    """The SAVE door for a tenant's company tags: ``(stored, refusals)``.

    ``stored`` is the map as it is kept (each value normalised: line endings as ``\\n``, outer
    blanks off) and is ``{}`` whenever ``refusals`` is not empty — nothing is stored on any
    refusal. Never raises."""
    if not isinstance(raw, Mapping):
        return {}, ("as tags personalizadas são um objeto {nome: valor}",)
    if len(raw) > MAX_CUSTOM_TAGS:
        return {}, (f"{len(raw)} tags personalizadas; o máximo é {MAX_CUSTOM_TAGS}",)
    refusals: list[str] = []
    stored: dict[str, str] = {}
    for name, value in raw.items():
        why = custom_tag_problems(name, value)
        if why:
            refusals += why
        elif isinstance(name, str) and isinstance(value, str):  # what the rule just accepted
            stored[name] = _custom_value(value)
    return ({}, tuple(refusals)) if refusals else (stored, ())


def parse_custom_tags(raw: object) -> "dict[str, str]":
    """The TURN door: the tags of ``raw`` the save would keep, normalised — every other entry
    dropped, never a refusal. A malformed map costs the tenant its tags, never the contact a
    reply; the fill then asks for each one the template uses."""
    if not isinstance(raw, Mapping):
        return {}
    return {name: _custom_value(value) for name, value in raw.items()
            if isinstance(name, str) and isinstance(value, str)
            and not custom_tag_problems(name, value)}


def _company_tags(raw: "Mapping[str, str] | Iterable[str]") -> "dict[str, Optional[str]]":
    """``custom_tags=`` as ``{name: value or None}``: a mapping keeps its values (so a subject
    can be checked), an iterable of names has none. Whatever cannot be a tag is dropped."""
    if isinstance(raw, Mapping):
        return {k: (v if isinstance(v, str) else None) for k, v in raw.items()
                if is_custom_tag_name(k)}
    if isinstance(raw, str):
        return {raw: None} if is_custom_tag_name(raw) else {}
    try:
        return {k: None for k in raw if is_custom_tag_name(k)}
    except TypeError:          # not iterable: a caller that handed over something else
        return {}


# ── the template ─────────────────────────────────────────────────────────────────────────────

def template_fields(subject: str, body: str) -> "tuple[str, ...]":
    """The markers a template uses, subject first, in order of first appearance."""
    return tuple(dict.fromkeys(markers_cited(subject or "") + markers_cited(body or "")))


def _bracket_problems(text: str, where: str, phase: str,
                      tags: "Optional[Mapping[str, Optional[str]]]" = None,
                      any_company_tag: bool = False) -> "list[str]":
    """Every ``[`` in ``text`` that does not open a marker of :data:`EMAIL_FIELDS` nor one of
    the tenant's company ``tags`` — named, with its position, listing every marker that exists.
    ``any_company_tag`` accepts every name a company tag CAN have (:func:`is_custom_tag_name`),
    declared or not."""
    out: list[str] = []
    tags = tags or {}
    allowed = ", ".join(known_markers()) + (
        "; e os da empresa: " + ", ".join(f"[{n}]" for n in tags) if tags else "")
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
        if name in EMAIL_FIELDS:
            continue
        if name in tags or (any_company_tag and is_custom_tag_name(name)):
            continue
        if name in REFUSED_FIELDS:
            since = _FIELD_PHASE.get(name)
            if since is not None and _PHASES.index(phase) >= _PHASES.index(since):
                continue
            out.append(f"no {where}: {REFUSED_FIELDS[name]}")
            continue
        out.append(f"no {where}, [{name}] não é um marcador; os marcadores são {allowed}")
    return out


def validate_template(subject: str, body: str, *, phase: str = "E1",
                      persona: "Optional[str]" = None,
                      custom_tags: "Mapping[str, str] | Iterable[str]" = (),
                      any_company_tag: bool = False) -> "tuple[str, ...]":
    """Every reason this template cannot be saved, in words — ``()`` when it is valid.

    Never raises. Each reason is a sentence the tenant's admin reads (the host answers 400 with
    the list), so it names what is wrong and where, and lists the markers that DO exist.

    ``persona`` — the persona the template is saved for. It changes nothing: the markers are ONE
    list for every persona (the owner's rule, 2026-10-21), and a marker this persona cannot fill
    is the send's question, not the save's refusal (:func:`fields_for`, :class:`Missing`). It is
    still accepted so that a caller written when it narrowed the list keeps working.

    ``custom_tags`` — the tenant's company tags: a mapping ``{name: value}`` or just the names.
    Each is a marker of this template beside the thirteen, in any persona; a name that cannot be
    a tag (:func:`is_custom_tag_name`) is ignored, so it unlocks nothing. With the VALUES, a tag
    whose value spans lines is refused in the subject. ``()`` — no company tag: the verdict of
    before, byte for byte.

    ``any_company_tag`` — the TURN's reading: every name a company tag can have is accepted,
    declared or not, because a template whose tag was removed after it was saved still exists —
    the fill says the tag is missing and the send asks (:data:`CUSTOM_TAG_REMOVED`). The SAVE
    passes the tenant's tags and leaves this ``False``.
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
    tags = _company_tags(custom_tags)
    out += _bracket_problems(subject, "assunto", phase, tags, any_company_tag)
    out += _bracket_problems(body, "corpo", phase, tags, any_company_tag)
    for name in markers_cited(subject):
        if name in SUBJECT_FORBIDDEN:
            out.append(f"[{name}] não pode ir no assunto (tem várias linhas ou é texto livre)")
        elif "\n" in _custom_value(tags.get(name) or ""):
            out.append(f"[{name}] não pode ir no assunto (o valor dessa tag da empresa tem "
                       "várias linhas)")
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

    ``custom_tags`` — the tenant's company tags, ``{name: value}`` (:func:`parse_custom_tags`),
    from the host: a FIXED value of the tenant, the same for every persona and every recipient.
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
    custom_tags: "Mapping[str, str]" = field(default_factory=dict)


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


def fill_email_fields(fields: "Iterable[str]", context: EmailContext, *,
                      persona: "Optional[str]" = None
                      ) -> "tuple[dict[str, str], tuple[Missing, ...]]":
    """Fill ``fields`` (a template's markers) from ``context`` — ``(values, missing)``.

    Never raises. ``missing`` is empty exactly when every requested field has a value AND the
    recipient has an address — ``[email]`` is checked always, because it is where the e-mail
    goes, whether or not the body quotes it. A free text given to a template with no
    ``[conteudo]`` is also a ``Missing``: it would be dropped in silence, and the requester asked
    for it to be said.

    ``persona`` — the persona the e-mail is composed FOR. A marker it cannot fill
    (:func:`fields_for`: another persona's provider reads it) is a ``Missing`` that names the
    marker and WHO reads it, and is never taken from ``context`` — a value there was not this
    persona's to read. ``None`` fills every marker from the context, exactly as before.

    A field that is not one of the thirteen and has a company tag's name
    (:func:`is_custom_tag_name`) is a company tag: filled from ``context.custom_tags`` FIRST and
    in ANY persona, because its value is the tenant's, not a persona's read. One the context does
    not carry was removed after the template was saved — a ``Missing`` with
    :data:`CUSTOM_TAG_REMOVED`; one whose stored value the save would refuse is a ``Missing``
    with that refusal. Neither is ever rendered blank.
    """
    wanted = tuple(dict.fromkeys(f for f in fields
                                 if f in EMAIL_FIELDS or is_custom_tag_name(f)))
    values: dict[str, str] = {}
    missing: list[Missing] = []
    mine = fields_for(persona)
    tags = context.custom_tags if isinstance(context.custom_tags, Mapping) else {}

    def miss(name: str, reason: str) -> None:
        source = EMAIL_FIELDS[name].source if name in EMAIL_FIELDS else CUSTOM_TAG_SOURCE
        missing.append(Missing(name, source, reason))

    who = context.recipient_name.strip() or context.professor.strip() or "o destinatário"
    month_num = _month_numeric(context.month)
    if not context.recipient_email.strip():
        miss("email", f"{who} não tem e-mail no cadastro")
    for name in wanted:
        if name not in EMAIL_FIELDS:
            # A company tag: the tenant's fixed value, before any provider, in any persona.
            if name not in tags:
                miss(name, CUSTOM_TAG_REMOVED)
            elif custom_tag_problems(name, tags[name]):
                miss(name, "; ".join(custom_tag_problems(name, tags[name])))
            else:
                values[name] = _custom_value(tags[name])
        elif name not in mine:
            owner = provider_of(name)
            miss(name, f"o template usa [{name}], que esta persona não consegue preencher"
                       + (f": só a {owner.label} ({owner.persona}) o lê" if owner else ""))
        elif name == "nome":
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
    "date_words", "CUSTOM_TAG_NAME", "MAX_CUSTOM_TAG_CHARS", "MAX_CUSTOM_TAGS",
    "CUSTOM_TAG_SOURCE", "CUSTOM_TAG_REMOVED", "is_custom_tag_name", "custom_tag_problems",
    "normalise_custom_tags", "parse_custom_tags",
]
