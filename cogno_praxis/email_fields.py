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

**The DEFAULT markers are the eight that serve every persona; a persona's own are added only to
its template (2026-10-22).** The owner's rule: «vamos deixar somente as tags que servem para
todos, tags especificas precisam ser adicionadas». :data:`GENERIC_FIELDS` are the default list —
filled from what every turn has (the tenant's records, the tenant itself, the request, the
clock): ``[nome]``, ``[email]``, ``[empresa]``, ``[mes]``, ``[data]``, ``[assinatura]``,
``[solicitante]``, ``[conteudo]`` — and :func:`known_markers` with no persona answers them.
Everything else is read by ONE persona and is declared by that persona's
:class:`FieldProvider`: today only the coordinator's (``[aulas]``, ``[disciplinas]``,
``[valor_por_aula]``, ``[valores_por_bonus]``, ``[total]``). Those are valid in THAT persona's
template and in no other: :func:`validate_template` refuses one anywhere else — and in a template
saved with no persona — with a sentence that names the marker and the persona it belongs to
(«[aulas] é uma tag da coordenação (COORDINATOR): só pode ser usada no template dessa
persona»).
:data:`EMAIL_FIELDS` is the union, derived — never typed: every name the fill knows, and every
name a company tag may never take. From 2026-10-21 until this rule the thirteen were valid in
every persona's template (a marker the persona could not fill was asked at the send); from E3
(2026-10-07) until 2026-10-21 they were refused by persona, as now.

**Validating and filling with NO persona answer different lists, on purpose.** The save asks
«which markers may a template use», and a template nobody owns has only the default list: no
persona's read stands behind a coordination figure there. The fill asks «what can be filled from
THIS context», and with no persona it fills every marker the context carries, byte for byte as it
always did — a caller that built the context itself (a test, a doc check, a host from before
personas) is the reader of everything in it. A host that knows the persona passes it to both.

A provider DECLARES fields; it does not read them. Which service answers for a provider's
fields is the host's wiring (:func:`provider_fields` tells it which providers a template needs,
and a template of generic markers alone needs none). This module imports no service.

**The tenant's own markers — company tags with a FIXED value (2026-10-21).** Beside the
markers above, a tenant may declare tags of its own: ``{name: value}``, valid in EVERY persona's
template (a fixed value of the tenant serves every persona). The name is
:data:`CUSTOM_TAG_NAME` (``[a-z][a-z0-9_]{1,30}``) and is never a marker of
:data:`EMAIL_FIELDS` — the UNION, so the coordination's five stay reserved in every persona
although the default list is the eight — nor a name of :data:`REFUSED_FIELDS`; the value is plain text, one line or
several, at most :data:`MAX_CUSTOM_TAG_CHARS` characters — the business's DATA, never an
instruction. :func:`normalise_custom_tags` is the SAVE door (every refusal named) and
:func:`parse_custom_tags` the TURN's (tolerant: it drops what the save would refuse). The value
is filled deterministically by :func:`fill_email_fields`, from ``EmailContext.custom_tags``,
before any provider and in any persona: a value is the tenant's, not a persona's read.
:func:`validate_template` accepts the tenant's tag names (``custom_tags=``); a template whose tag
was removed after it was saved is refused by the save and kept by the turn, which is handed the
names the tenant REMOVED (``removed_tags=``), and the fill returns it as a :class:`Missing` —
«tag personalizada removida» — so the send asks the requester instead of sending. A name the
tenant never declared (a typo) is refused at both doors, as any unknown marker always was. Tags
filled by data (a provider, code), tags of one persona only and HTML values are not here: a tag's
value is plain text, and the HTML form of an e-mail (below) shows it escaped.

**FREE company tags — no fixed value, filled from the CONVERSATION (2026-10-22).** The owner:
«preciso q seja flexivel e chamada pelo usuario»; «o template terá tags que devem ser preenchidas
conforme as mensagens com o agente». A company tag whose stored value is EMPTY (``""`` after the
normalisation) is FREE: :func:`custom_tag_problems` no longer refuses it, and the map keeps it as
``{name: ""}`` — ONE map, so every string the G package stored (never empty: its save door
refused that) still reads as the FIXED tag it was. :func:`free_tags` names them. The value comes
from what the person who asked SAID: ``EmailContext.free_tag_values``, which the host takes from
the executor's call. :func:`fill_email_fields` fills a free tag from it as ONE line of plain text
(every run of blanks and line breaks becomes one space, so it never breaks a subject; at most
:data:`MAX_CUSTOM_TAG_CHARS` characters, no control character); a free tag the conversation did
not fill is a :class:`Missing` — :data:`CUSTOM_TAG_FREE_MISSING`, from
:data:`CUSTOM_TAG_FREE_SOURCE` — so the send ASKS, the path that already existed. A value the
conversation gives for a FIXED tag, a standard marker or a name that is no tag changes nothing:
a fixed tag stays fixed. The free tag is a company tag in every other respect: the same name
grammar and the same reservation (the thirteen of :data:`EMAIL_FIELDS`, the reserved names), the
same removed path. A free tag may carry a HINT for the person filling it («a disciplina da aula
remarcada»): plain text of the tenant, ONE line, at most :data:`MAX_CUSTOM_TAG_HINT_CHARS`
characters, only for a free tag — :func:`normalise_custom_tag_hints` (the save door),
:func:`parse_custom_tag_hints` (the turn's), ``EmailContext.custom_tag_hints`` — and the question
names it. A host that puts a hint in a prompt shapes and fences it like any text of the tenant.

**A field with no value STOPS the send.** :func:`fill_email_fields` returns ``(values, missing)``
and never raises; each :class:`Missing` names the field, where it should have come from and why
it is not there, in the vertical's own words. The host turns a non-empty ``missing`` into a
QUESTION to the requester instead of a proposal. :func:`render_email` refuses to run with a
marker that has no value — it is never reached with one.

**The HTML form — tables for an e-mail that carries data (2026-10-22).** The owner's order:
«qdo for enviar cronograma ou algum dado especifico, colocar em formato tabular e visualmente
agradavel», and his model e-mail. :func:`render_email_forms` gives ``(subject, text, html)``.
:func:`render_email_html` renders the SAME e-mail as an HTML document:
- the classes as one table PER CLASS GROUP under its «Turma X» title, each discipline's cell in a
  colour that is the same across the whole e-mail (:func:`record_colors`) — drawn by the
  GENERIC renderer, :func:`records_html`, from a list of records the coordinator produces;
- the pay values as two-column tables, the disciplines as a list;
- the tenant's text as simple rich text (paragraphs, «•»/«·» lists, short «…:» titles, its URLs as
  links);
- a header with the sender's name and, when the tenant configured one, its signature block
  (:class:`EmailAppearance`, saved through :func:`normalise_email_appearance`).

The host sends it beside the text as ``multipart/alternative``. The TEXT is what the requester was
shown and confirmed, and :func:`email_digest` is taken of it. It moved in one place only: ``[aulas]``
is a «Turma X» block per class group, its lines with the weekday. It also gains the configured
signature's lines when the e-mail goes out as HTML.

A template whose body uses no provider's marker renders no HTML at all (``""``) and its e-mail
goes out as the text it always was. Every value and the template's own text are escaped and the
styles are inline. The only images are the logo and the icons the tenant configured
(``http``/``https``, with ``alt``); nothing else is loaded. A table is drawn only from rows whose
text IS the value the text part carries.

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
import html
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from cogno_praxis.coordinator.pay import (PayEstimate, _condition_lines, bonus_band_rows, bonus_mark,
                                          fmt_money)

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
    """The markers ``persona`` can FILL: the generic ones and its own provider's — for a persona,
    also the markers its template may use (:func:`known_markers`).

    A host composing an e-mail asks it, and a marker outside it comes out as ``missing``.

    ``None`` — the caller does not say whose it is — answers EVERY marker: the FILL with no
    persona reads everything its context carries. The SAVE with no persona does not: it offers
    the default list (:func:`known_markers`; the module docstring says why the two differ). Any
    string, the empty one included, is a persona."""
    if persona is None:
        return EMAIL_FIELDS
    p = provider_for(persona)
    if p is None:
        return GENERIC_FIELDS
    return MappingProxyType({**GENERIC_FIELDS, **{f.name: f for f in p.fields}})


def _template_fields_for(persona: "Optional[str]") -> "Mapping[str, FieldSpec]":
    """The markers a template of ``persona`` may use: the default list (:data:`GENERIC_FIELDS`)
    with no persona, else the generic ones and its own provider's (:func:`fields_for`)."""
    return GENERIC_FIELDS if persona is None else fields_for(persona)


def known_markers(persona: "Optional[str]" = None) -> "tuple[str, ...]":
    """``("[nome]", "[email]", …)`` — the markers a template of ``persona`` may use, as a person
    reads them, generic markers first. With no ``persona``, the DEFAULT list: the eight generic
    markers that serve every persona. With one, the generic ones and that persona's own (the
    COORDINATOR's thirteen) — exactly what :func:`validate_template` accepts for it and lists in
    its refusals."""
    return tuple(f"[{n}]" for n in _template_fields_for(persona))


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
#: Where a FREE company tag's value comes from — the ``source`` of its :class:`Missing`.
CUSTOM_TAG_FREE_SOURCE = "o que o solicitante disser na conversa"
#: The reason a FREE company tag has no value: the conversation did not say it. The tenant's
#: hint, when there is one, follows after a colon.
CUSTOM_TAG_FREE_MISSING = "o pedido não disse o que pôr nesta tag"
#: The longest HINT a free tag may carry, counted after it is stripped.
MAX_CUSTOM_TAG_HINT_CHARS = 120
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
    it can. Never raises. Each sentence names the tag, so a list of them needs no index.

    An EMPTY value (blanks only included) is a FREE tag, not a refusal (2026-10-22): its value
    comes from the conversation. The NAME is checked first, so a free tag is held to the same
    grammar and the same reservation as a fixed one."""
    if not isinstance(name, str) or CUSTOM_TAG_NAME.fullmatch(name) is None:
        shown = name[:40] if isinstance(name, str) else type(name).__name__
        return (f"«{shown}» não serve como nome de tag: só letras minúsculas sem acento, "
                "algarismos e «_», a começar por uma letra, de 2 a 31 caracteres",)
    if name in EMAIL_FIELDS:
        # Every name of the UNION is refused — never only the default list's, or a tag named
        # [aulas] would collide with what the coordination computes. Only the WORDS differ: a
        # persona's own marker is not «padrão» (2026-10-22).
        owner = provider_of(name)
        kind = f"uma tag da {owner.label}" if owner is not None else "um marcador padrão"
        return (f"[{name}] já é {kind} ({EMAIL_FIELDS[name].source}); escolha outro nome",)
    if name in REFUSED_FIELDS:
        return (f"[{name}] é um nome reservado: {REFUSED_FIELDS[name]}",)
    if not isinstance(value, str):
        return (f"o valor de [{name}] tem de ser texto",)
    text = _custom_value(value)
    if any((ord(c) < 32 or ord(c) == 127) and c not in _ALLOWED_CONTROLS for c in text):
        return (f"o valor de [{name}] tem um caractere de controle; só texto simples "
                "(com quebras de linha e tabulações)",)
    if len(text) > MAX_CUSTOM_TAG_CHARS:
        return (f"o valor de [{name}] tem {len(text)} caracteres; o máximo é "
                f"{MAX_CUSTOM_TAG_CHARS}",)
    return ()


def free_tags(tags: object) -> "tuple[str, ...]":
    """The FREE tags of ``tags`` (a map the turn door read, :func:`parse_custom_tags`): the names
    whose value is empty, in the map's order. Never raises; a name that cannot be a tag is none."""
    if not isinstance(tags, Mapping):
        return ()
    return tuple(n for n, v in tags.items()
                 if is_custom_tag_name(n) and isinstance(v, str) and not _custom_value(v))


def free_value(value: object) -> str:
    """A value the conversation gave a free tag, as it is filled: ONE line — every run of blanks
    and line breaks one space, the outer ones off. ``""`` for anything that is not text."""
    return " ".join(value.split()) if isinstance(value, str) else ""


def free_value_problems(name: str, value: object) -> "tuple[str, ...]":
    """Every reason the conversation's ``value`` cannot fill the free tag ``name`` — ``()`` when
    it can (an empty one included: that is a value nobody said, not a bad one). The fixed value's
    sentences, so the requester reads one rule."""
    if not isinstance(value, str):
        return (f"o valor de [{name}] tem de ser texto",)
    text = free_value(value)
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        return (f"o valor de [{name}] tem um caractere de controle; só texto simples",)
    if len(text) > MAX_CUSTOM_TAG_CHARS:
        return (f"o valor de [{name}] tem {len(text)} caracteres; o máximo é "
                f"{MAX_CUSTOM_TAG_CHARS}",)
    return ()


def custom_tag_hint_problems(name: object, hint: object,
                             tags: "Mapping[str, str]") -> "tuple[str, ...]":
    """Every reason ``hint`` cannot be the hint of the company tag ``name``, given the tenant's
    ``tags`` (as stored) — ``()`` when it can. Never raises. A hint belongs to a FREE tag only:
    a fixed one is filled by its value and asks nobody. It is the tenant's plain text, one line,
    at most :data:`MAX_CUSTOM_TAG_HINT_CHARS` characters."""
    known = tags if isinstance(tags, Mapping) else {}
    if (not isinstance(name, str) or name not in known or not is_custom_tag_name(name)
            or not isinstance(known[name], str)):
        shown = name[:40] if isinstance(name, str) else type(name).__name__
        return (f"a dica de «{shown}» não é de nenhuma tag da empresa",)
    if _custom_value(known[name]):
        return (f"[{name}] tem valor fixo: a dica só serve a uma tag livre (sem valor)",)
    if not isinstance(hint, str):
        return (f"a dica de [{name}] tem de ser texto",)
    text = hint.strip()
    if len(text.splitlines()) > 1:
        return (f"a dica de [{name}] tem de ser uma linha só",)
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        return (f"a dica de [{name}] tem um caractere de controle; só texto simples",)
    if len(text) > MAX_CUSTOM_TAG_HINT_CHARS:
        return (f"a dica de [{name}] tem {len(text)} caracteres; o máximo é "
                f"{MAX_CUSTOM_TAG_HINT_CHARS}",)
    return ()


def normalise_custom_tag_hints(raw: object, tags: "Mapping[str, str]"
                               ) -> "tuple[dict[str, str], tuple[str, ...]]":
    """The SAVE door for the hints of the tenant's FREE tags: ``(stored, refusals)``.

    ``tags`` is the map as it will be stored (:func:`normalise_custom_tags`). ``None`` is no
    hints. An empty hint is no hint (not stored). ``stored`` is ``{}`` whenever ``refusals`` is
    not empty. Never raises."""
    if raw is None:
        return {}, ()
    if not isinstance(raw, Mapping):
        return {}, ("as dicas das tags são um objeto {nome: dica}",)
    refusals: list[str] = []
    stored: dict[str, str] = {}
    for name, hint in raw.items():
        why = custom_tag_hint_problems(name, hint, tags)
        if why:
            refusals += why
        elif isinstance(name, str) and isinstance(hint, str) and hint.strip():
            stored[name] = hint.strip()
    return ({}, tuple(refusals)) if refusals else (stored, ())


def parse_custom_tag_hints(raw: object, tags: "Mapping[str, str]") -> "dict[str, str]":
    """The TURN door for the hints: those the save would keep, stripped — every other entry
    dropped, never a refusal."""
    if not isinstance(raw, Mapping):
        return {}
    return {name: hint.strip() for name, hint in raw.items()
            if isinstance(name, str) and isinstance(hint, str) and hint.strip()
            and not custom_tag_hint_problems(name, hint, tags)}


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
                      removed: "frozenset[str]" = frozenset(),
                      persona: "Optional[str]" = None) -> "list[str]":
    """Every ``[`` in ``text`` that does not open a marker a template of ``persona`` may use
    (:func:`known_markers`) nor one of the tenant's company ``tags`` — named, with its position,
    listing exactly the markers it may use. A marker of ANOTHER persona's provider is refused
    naming the persona it belongs to. A name in ``removed`` (a tag the tenant removed) is accepted
    too, and is not listed."""
    out: list[str] = []
    tags = tags or {}
    usable = _template_fields_for(persona)
    allowed = ", ".join(known_markers(persona)) + (
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
        if name in usable:
            continue
        owner = provider_of(name)
        if owner is not None:
            # A real marker, of a persona this template is not (or of no persona at all).
            out.append(f"no {where}, [{name}] é uma tag da {owner.label} ({owner.persona}): só "
                       f"pode ser usada no template dessa persona; os marcadores são {allowed}")
            continue
        if name in tags or name in removed:
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
                      removed_tags: "Iterable[str]" = ()) -> "tuple[str, ...]":
    """Every reason this template cannot be saved, in words — ``()`` when it is valid.

    Never raises. Each reason is a sentence the tenant's admin reads (the host answers 400 with
    the list), so it names what is wrong and where, and lists the markers that DO exist.

    ``persona`` — the persona the template is saved for. Its template may use the default list
    (the eight generic markers) and that persona's own (:func:`known_markers`); a marker of
    another persona's provider is refused, naming the persona it belongs to (the owner's rule,
    2026-10-22). ``None`` — a template nobody owns — may use the default list only; the fill with
    no persona still reads every marker (the module docstring says why the two differ). Any
    string, the empty one included, is a persona, compared as written (:func:`provider_for`).

    ``custom_tags`` — the tenant's company tags: a mapping ``{name: value}`` or just the names.
    Each is a marker of this template beside the persona's, in any persona; a name that cannot be
    a tag (:func:`is_custom_tag_name`) is ignored, so it unlocks nothing. With the VALUES, a tag
    whose value spans lines is refused in the subject. ``()`` — no company tag: the verdict of
    before, byte for byte.

    ``removed_tags`` — the TURN's reading: the names of company tags the tenant REMOVED. A
    template that cites one still exists — the fill says the tag is missing and the send asks
    (:data:`CUSTOM_TAG_REMOVED`) — so it is accepted here; a name never declared (a typo) is not
    one, and is refused as at the save. A name that cannot be a tag is ignored. The SAVE passes
    the tenant's tags and no removed ones.
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
    removed = frozenset(n for n in _company_tags(removed_tags) if n not in tags)
    out += _bracket_problems(subject, "assunto", phase, tags, removed, persona)
    out += _bracket_problems(body, "corpo", phase, tags, removed, persona)
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
    from the host: a FIXED value of the tenant, the same for every persona and every recipient;
    an EMPTY value is a FREE tag (:func:`free_tags`).

    ``free_tag_values`` — what the CONVERSATION said for the free tags, ``{name: text}``: the
    host takes it from the executor's call. Read for a free tag only; anything else in it is
    ignored. ``custom_tag_hints`` — the tenant's hints for its free tags
    (:func:`parse_custom_tag_hints`), named in the question when a value is missing.
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
    free_tag_values: "Mapping[str, str]" = field(default_factory=dict)
    custom_tag_hints: "Mapping[str, str]" = field(default_factory=dict)


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


# ── records: the one shape a table is drawn from (2026-10-22) ──────────────────────────────────
#
# The owner's rule: «preciso de algo genérico» — a new persona's e-mail is made with tags, never
# with code. So nothing here draws «the classes»: it draws a LIST OF RECORDS, each a mapping of
# simple keys to text, and the coordinator's [aulas] is just one producer of such a list
# (:func:`_aulas_records`). Three keys have a meaning, compared folded (case and accents aside):
#
# * ``turma`` — the records are split into one block per value, titled «Turma <value>», the blocks
#   in the order of the value (a list without it is one block, untitled);
# * ``disciplina`` — in the HTML, each distinct value has one colour across the whole e-mail;
# * a record whose keys are all among ``mes``/``dia``/``data``/``horario``/``disciplina``/``turma``
#   and that has ``data`` and ``disciplina`` is written as a dated line, «06/10 (ter) 19:00 —
#   Disciplina»; any other record as «chave: valor · …».

#: A runaway guard: the most records one list may carry.
MAX_RECORDS = 500
_GROUP_KEY = "turma"
_COLOR_KEY = "disciplina"
_DATED_KEYS = frozenset({"mes", "dia", "data", "horario", "disciplina", "turma"})
_SHORT_DATE = re.compile(r"(\d{1,2}/\d{1,2})/\d{2,4}")


def _fold_key(key: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", key)
                   if not unicodedata.combining(c)).casefold().strip()


def as_records(value: object) -> "Optional[list[dict[str, str]]]":
    """``value`` as a list of records — each a ``{key: text}`` with non-blank string keys, a
    value that is not text written as text (``None`` as empty) — or ``None`` when it is not a
    non-empty list of mappings (or holds more than :data:`MAX_RECORDS`). Never raises."""
    if not isinstance(value, (list, tuple)) or not value or len(value) > MAX_RECORDS:
        return None
    out: "list[dict[str, str]]" = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        record: "dict[str, str]" = {}
        for k, v in item.items():
            if not isinstance(k, str) or not k.strip():
                return None
            record[k.strip()] = "" if v is None else (v if isinstance(v, str) else str(v)).strip()
        out.append(record)
    return out


def _field(record: "Mapping[str, str]", name: str) -> str:
    """The value of the key of ``record`` that folds to ``name`` — ``""`` when there is none."""
    for k, v in record.items():
        if _fold_key(k) == name:
            return v
    return ""


def _group_title(value: str) -> str:
    """«Turma <value>» — the value itself when it already says «Turma …»."""
    v = value.strip()
    return v if _fold_key(v).startswith("turma") else f"Turma {v}"


def _record_groups(records: "Sequence[Mapping[str, str]]"
                   ) -> "list[tuple[str, list[Mapping[str, str]]]]":
    """``[(group value, records)]`` — one group per value of the ``turma`` key, in the order of
    the value; the records keep their order inside a group. No ``turma`` key → one group, ``""``."""
    if not any(_fold_key(k) == _GROUP_KEY for r in records for k in r):
        return [("", list(records))]
    groups: "dict[str, list[Mapping[str, str]]]" = {}
    for r in records:
        groups.setdefault(_field(r, _GROUP_KEY), []).append(r)
    # By the CODE: «B2» and «Turma A1» are ordered as «Turma B2» and «Turma A1» are.
    return sorted(groups.items(), key=lambda kv: (_fold_key(_group_title(kv[0])), kv[0]))


def _record_line(record: "Mapping[str, str]") -> str:
    """One record as a line of text: the dated form when its keys are the known ones, else
    «chave: valor · …» (the group key and the empty values left out)."""
    keys = {_fold_key(k) for k in record}
    if keys <= _DATED_KEYS and _field(record, "data") and _field(record, "disciplina"):
        date_text = _field(record, "data")
        m = _SHORT_DATE.fullmatch(date_text)
        stamp = (m.group(1) if m else date_text)
        stamp += f" ({_field(record, 'dia')})" if _field(record, "dia") else ""
        stamp += f" {_field(record, 'horario')}" if _field(record, "horario") else ""
        return f"{stamp} — {_field(record, 'disciplina')}"
    return " · ".join(f"{k}: {v}" for k, v in record.items() if v and _fold_key(k) != _GROUP_KEY)


def records_text(records: object) -> str:
    """A list of records as TEXT: one line per record (:func:`_record_line`), under a «Turma X»
    title per group when the records carry a ``turma``, a blank line between groups. ``""`` for
    anything that is not a list of records."""
    recs = as_records(records)
    if recs is None:
        return ""
    blocks = []
    for value, group in _record_groups(recs):
        lines = [_record_line(r) for r in group]
        blocks.append("\n".join(([_group_title(value)] if value else []) + lines))
    return "\n\n".join(blocks)


#: ``date.weekday()`` → the abbreviated weekday a Brazilian timetable writes (2026-10-22: the
#: owner's model e-mail has a «Dia» column, and the text line carries it too).
_WEEKDAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def _weekday(day: date) -> str:
    return _WEEKDAYS[day.weekday()]


def _aulas_records(classes: "Iterable[EmailClass]") -> "list[dict[str, str]]":
    """``[aulas]`` as a list of records — the coordinator's classes, in order, keyed by the
    convention above: ``mês``, ``dia``, ``data`` (dd/mm/aa), ``horário`` (when any class has an
    hour; ``""`` for one without — never a guessed hour), ``disciplina`` and ``turma``. The text
    and the tables are drawn from this list by the GENERIC renderer; nothing here is particular to
    classes."""
    ordered = _ordered_classes(classes)
    timed = any(c.time for c in ordered)
    return [{"mês": _PT_MONTHS[c.when.month], "dia": _weekday(c.when),
             "data": c.when.strftime("%d/%m/%y"), **({"horário": c.time} if timed else {}),
             "disciplina": c.subject, "turma": c.turma} for c in ordered]


def _aulas_text(classes: "Iterable[EmailClass]") -> str:
    """``[aulas]`` as text: :func:`records_text` of :func:`_aulas_records`."""
    return records_text(_aulas_records(classes))


def _ordered_classes(classes: "Iterable[EmailClass]") -> "list[EmailClass]":
    """The month's classes in the order ``[aulas]`` lists them — by day, then hour (a class with no
    hour after the timed ones of its day). ONE definition: the text and the HTML table read it."""
    return sorted(classes, key=lambda c: (c.when, c.time or "99:99"))


def _subjects(classes: "Iterable[EmailClass]") -> "list[str]":
    """``[disciplinas]``: each discipline once, case-folded alphabetical — for the text and the
    HTML list alike."""
    return sorted({c.subject for c in classes}, key=lambda s: (s.casefold(), s))


def _bonus_rows(est: PayEstimate) -> "list[tuple[str, str, bool]]":
    """``(label, value, applied)`` per line of ``[valores_por_bonus]`` — the pay block's own rows
    (:func:`cogno_praxis.coordinator.pay.bonus_band_rows`, ONE definition: the block the tool
    prints and the e-mail cannot list different figures). The text and the HTML table read them."""
    return bonus_band_rows(est)


def _bonus_mark(est: PayEstimate) -> str:
    return bonus_mark(est)


def _bonus_condition(est: PayEstimate) -> "list[str]":
    """The response-rate condition the bands hang on, as its non-empty lines (``[]`` when the
    rules declare none)."""
    return [ln for ln in _condition_lines(est) if ln]


def _bonus_value(est: PayEstimate) -> str:
    """``[valores_por_bonus]``: «Sem bônus» and one line per DECLARED band, always — the levels
    the rules declare, not the hypotheses (which are empty once the result was read). The
    applied band is marked only when the bonus is DETERMINED; with ``not_found``/``gap`` no line
    is marked and none is chosen."""
    mark = _bonus_mark(est)
    lines = [f"{label}: {value}" + (mark if applied else "")
             for label, value, applied in _bonus_rows(est)]
    cond = _bonus_condition(est)
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

    A FREE company tag (stored value empty, :func:`free_tags`) is filled from
    ``context.free_tag_values`` — what the conversation said — as one line of plain text
    (:func:`free_value`). Not said (absent or blank) → a ``Missing`` with
    :data:`CUSTOM_TAG_FREE_MISSING` and the tenant's hint, from :data:`CUSTOM_TAG_FREE_SOURCE`;
    said in a form the rule refuses (:func:`free_value_problems`) → a ``Missing`` with that
    sentence. A conversation value for anything that is not a free tag is never read.
    """
    wanted = tuple(dict.fromkeys(f for f in fields
                                 if f in EMAIL_FIELDS or is_custom_tag_name(f)))
    values: dict[str, str] = {}
    missing: list[Missing] = []
    mine = fields_for(persona)
    tags = context.custom_tags if isinstance(context.custom_tags, Mapping) else {}
    said = context.free_tag_values if isinstance(context.free_tag_values, Mapping) else {}
    hints = context.custom_tag_hints if isinstance(context.custom_tag_hints, Mapping) else {}

    def miss(name: str, reason: str, source: str = "") -> None:
        source = source or (EMAIL_FIELDS[name].source if name in EMAIL_FIELDS
                            else CUSTOM_TAG_SOURCE)
        missing.append(Missing(name, source, reason))

    def fill_free(name: str) -> None:
        given = said.get(name)
        if given is None or (isinstance(given, str) and not free_value(given)):
            hint = hints.get(name)
            shown = (hint.strip() if isinstance(hint, str)
                     and not custom_tag_hint_problems(name, hint, tags) else "")
            miss(name, CUSTOM_TAG_FREE_MISSING + (f": {shown}" if shown else ""),
                 CUSTOM_TAG_FREE_SOURCE)
        elif free_value_problems(name, given):
            miss(name, "; ".join(free_value_problems(name, given)), CUSTOM_TAG_FREE_SOURCE)
        else:
            values[name] = free_value(given)

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
            elif not _custom_value(tags[name]):
                fill_free(name)                  # a FREE tag: what the conversation said
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
        values[name] = _aulas_text(context.classes)
    elif name == "disciplinas":
        values[name] = "\n".join(_subjects(context.classes))
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


# ── the HTML form (2026-10-22) ────────────────────────────────────────────────────────────────
#
# The owner's order: an e-mail that carries specific data goes out readable at a glance — the
# classes in a table per class group, the values in a table, the tenant's text as paragraphs,
# lists and section titles, and the tenant's signature block. The TEXT form is what the requester
# is shown and confirms, and :func:`email_digest` is taken of it; the HTML is the SAME e-mail in
# another dress, sent beside the text as ``multipart/alternative`` — never a second text.

# ── the tenant's e-mail appearance ──────────────────────────────────────────────────────────

#: The fields of a tenant's «Aparência do e-mail». No free HTML: every one is plain text, a colour,
#: an e-mail, a phone or a URL, validated at the SAVE door and escaped at the render.
APPEARANCE_FIELDS = ("sender_name", "accent_color", "logo_url", "department", "email", "phone",
                     "site", "links")
#: The keys of one social link: its name (shown as the link text), its URL, and an optional icon.
APPEARANCE_LINK_FIELDS = ("label", "url", "icon_url")
MAX_APPEARANCE_TEXT = 80
MAX_APPEARANCE_URL = 500
MAX_SOCIAL_LINKS = 4
MAX_LINK_LABEL = 30
#: The only URL schemes a link, the logo or an icon may use.
APPEARANCE_URL_SCHEMES = ("http", "https")
_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_APPEARANCE_EMAIL = re.compile(r"[^@\s<>\"'()\[\]]+@[^@\s<>\"'()\[\]]+\.[^@\s<>\"'()\[\]]+")
_PHONE = re.compile(r"[0-9+()\-. ]{4,30}")
_URL_FORBIDDEN = frozenset(" \t\r\n\"'<>\\`")
_LABELS = {"sender_name": "o nome do remetente", "accent_color": "a cor de destaque",
           "logo_url": "o logótipo", "department": "o departamento", "email": "o e-mail",
           "phone": "o telefone", "site": "o site", "links": "os links das redes",
           "label": "o nome", "url": "o endereço", "icon_url": "o ícone"}


@dataclass(frozen=True)
class SocialLink:
    """One social link of the signature: its NAME is the link text; ``icon_url`` (optional) is a
    small image shown instead, with the name as its ``alt``."""
    label: str
    url: str
    icon_url: str = ""


@dataclass(frozen=True)
class EmailAppearance:
    """A tenant's «Aparência do e-mail» — what dresses the HTML form of its e-mails. Every field
    is optional; an empty one is simply not drawn. Build it with :func:`parse_email_appearance`
    (the TURN door) from what :func:`normalise_email_appearance` (the SAVE door) stored."""
    sender_name: str = ""
    accent_color: str = ""
    logo_url: str = ""
    department: str = ""
    email: str = ""
    phone: str = ""
    site: str = ""
    links: "tuple[SocialLink, ...]" = ()

    @property
    def has_signature(self) -> bool:
        """Whether the tenant configured a signature block: a logo, a line or a link."""
        return bool(self.logo_url or self.department or self.email or self.phone or self.site
                    or self.links)


def _text_problem(field: str, value: object, limit: int = MAX_APPEARANCE_TEXT) -> "Optional[str]":
    if not isinstance(value, str):
        return f"{_LABELS.get(field, field)} tem de ser texto"
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        return f"{_LABELS.get(field, field)} tem de ser uma linha de texto simples"
    if len(value.strip()) > limit:
        return f"{_LABELS.get(field, field)} tem {len(value.strip())} caracteres; o máximo é {limit}"
    return None


def _url_problem(field: str, value: object) -> "Optional[str]":
    """Why ``value`` is not a URL the appearance may hold — ``None`` when it is (or is empty).
    Only ``http``/``https`` with a host: ``javascript:``, ``data:``, a relative or a bare path are
    refused, and so is any blank or quote inside it."""
    what = _LABELS.get(field, field)
    if not isinstance(value, str):
        return f"{what} tem de ser um endereço (texto)"
    v = value.strip()
    if not v:
        return None
    if len(v) > MAX_APPEARANCE_URL:
        return f"{what} tem {len(v)} caracteres; o máximo é {MAX_APPEARANCE_URL}"
    if any(c in _URL_FORBIDDEN or ord(c) < 32 or ord(c) == 127 for c in v):
        return f"{what} não pode ter espaços, aspas nem os caracteres < > \\ `"
    parts = urllib.parse.urlsplit(v)
    if parts.scheme.lower() not in APPEARANCE_URL_SCHEMES or not parts.netloc:
        return f"{what} só aceita endereços http:// ou https:// (recebi «{v[:40]}»)"
    return None


def _links_problems(raw: object) -> "tuple[list[dict[str, str]], list[str]]":
    if not isinstance(raw, (list, tuple)):
        return [], ["os links das redes são uma lista de {label, url, icon_url}"]
    if len(raw) > MAX_SOCIAL_LINKS:
        return [], [f"{len(raw)} links de redes; o máximo é {MAX_SOCIAL_LINKS}"]
    out: "list[dict[str, str]]" = []
    why: "list[str]" = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, Mapping):
            why.append(f"o link {i} das redes tem de ser um objeto {{label, url, icon_url}}")
            continue
        extra = sorted(str(k) for k in item if k not in APPEARANCE_LINK_FIELDS)
        if extra:
            why.append(f"o link {i} das redes tem campos desconhecidos: {', '.join(extra)}")
        label, url, icon = item.get("label", ""), item.get("url", ""), item.get("icon_url", "")
        bad = [p for p in (_text_problem("label", label, MAX_LINK_LABEL),
                           _url_problem("url", url), _url_problem("icon_url", icon)) if p]
        if isinstance(label, str) and not label.strip():
            bad.append("tem de ter um nome")
        if isinstance(url, str) and not url.strip():
            bad.append("tem de ter um endereço")
        if bad:
            why += [f"o link {i} das redes: {b}" for b in bad]
        elif isinstance(label, str) and isinstance(url, str) and isinstance(icon, str):
            out.append({k: v for k, v in (("label", label.strip()), ("url", url.strip()),
                                          ("icon_url", icon.strip())) if v})
    return out, why


def normalise_email_appearance(raw: object) -> "tuple[dict[str, Any], tuple[str, ...]]":
    """The SAVE door for a tenant's e-mail appearance: ``(stored, refusals)``.

    ``stored`` keeps only the fields that carry a value, each normalised (outer blanks off, the
    colour in lower case), and is ``{}`` whenever ``refusals`` is not empty — nothing is stored
    on any refusal. Every refusal is a sentence that names the field. A URL (the site, the logo, a
    link, an icon) is ``http://`` or ``https://`` with a host, and nothing else. Never raises."""
    if not isinstance(raw, Mapping):
        return {}, ("a aparência do e-mail é um objeto {campo: valor}",)
    refusals: "list[str]" = []
    extra = sorted(str(k) for k in raw if k not in APPEARANCE_FIELDS)
    if extra:
        refusals.append(f"campos desconhecidos: {', '.join(extra)}; os campos são "
                        f"{', '.join(APPEARANCE_FIELDS)}")
    stored: "dict[str, Any]" = {}
    for name in ("sender_name", "department"):
        if name in raw:
            why = _text_problem(name, raw[name])
            if why:
                refusals.append(why)
            elif raw[name].strip():
                stored[name] = raw[name].strip()
    if "accent_color" in raw:
        v = raw["accent_color"]
        if not isinstance(v, str) or (v.strip() and not _COLOR.fullmatch(v.strip())):
            refusals.append("a cor de destaque é #RRGGBB (por exemplo #f6d55c)")
        elif v.strip():
            stored["accent_color"] = v.strip().lower()
    if "email" in raw:
        v = raw["email"]
        if not isinstance(v, str) or (v.strip() and (len(v.strip()) > 254
                                                     or not _APPEARANCE_EMAIL.fullmatch(v.strip()))):
            refusals.append("o e-mail da assinatura não é um endereço de e-mail")
        elif v.strip():
            stored["email"] = v.strip()
    if "phone" in raw:
        v = raw["phone"]
        if not isinstance(v, str) or (v.strip() and not _PHONE.fullmatch(v.strip())):
            refusals.append("o telefone só pode ter algarismos, espaços e + ( ) - . (4 a 30)")
        elif v.strip():
            stored["phone"] = v.strip()
    for name in ("logo_url", "site"):
        if name in raw:
            why = _url_problem(name, raw[name])
            if why:
                refusals.append(why)
            elif raw[name].strip():
                stored[name] = raw[name].strip()
    if "links" in raw:
        links, why_links = _links_problems(raw["links"])
        refusals += why_links
        if links and not why_links:
            stored["links"] = links
    return ({}, tuple(refusals)) if refusals else (stored, ())


def parse_email_appearance(raw: object) -> "Optional[EmailAppearance]":
    """The TURN door: the appearance ``raw`` describes, every field the save would refuse dropped
    on its own (a bad link costs that link, never the e-mail) — or ``None`` when nothing usable is
    left. Never raises."""
    if not isinstance(raw, Mapping):
        return None
    kept: "dict[str, Any]" = {}
    for name in APPEARANCE_FIELDS:
        if name in raw:
            stored, why = normalise_email_appearance({name: raw[name]})
            if not why:
                kept.update(stored)
    if isinstance(raw.get("links"), (list, tuple)) and "links" not in kept:
        # A list the save would refuse whole (one bad link): keep the good ones, at most four.
        good = [lk for lk in raw["links"][:MAX_SOCIAL_LINKS]
                if not normalise_email_appearance({"links": [lk]})[1]]
        if good:
            kept["links"] = normalise_email_appearance({"links": good})[0].get("links", [])
    if not kept:
        return None
    links = tuple(SocialLink(lk["label"], lk["url"], lk.get("icon_url", ""))
                  for lk in kept.pop("links", ()))
    return EmailAppearance(links=links, **kept)


def email_signature_text(appearance: "Optional[EmailAppearance]", context: EmailContext) -> str:
    """The signature block as TEXT lines — ``""`` unless the tenant configured one
    (:attr:`EmailAppearance.has_signature`). The name of the persona that signs (``[assinatura]``'s
    value; the tenant's name when it has none), the department, the phone, the e-mail, the site,
    and each social link as «name: URL». The HTML draws the SAME lines."""
    if appearance is None or not appearance.has_signature:
        return ""
    name = context.persona_name.strip() or context.tenant_name.strip()
    lines = [ln for ln in (name, appearance.department, appearance.phone, appearance.email,
                           appearance.site) if ln]
    lines += [f"{lk.label}: {lk.url}" for lk in appearance.links]
    return "\n".join(lines)


# ── the look ────────────────────────────────────────────────────────────────────────────────

#: Soft tones for the disciplines (orange, pink, yellow, light green, light blue, lilac). A tenant's
#: accent colour is put FIRST; without one, this palette as is.
DEFAULT_PALETTE = ("#fde2c4", "#f9d2e0", "#fff3b0", "#d8f0d2", "#d6e8fa", "#e6daf5")
#: The sober colours of an e-mail with no appearance: grey header cells, a navy name.
_INK = "#1f2328"
_NAVY = "#1f3a5f"
_HEAD_BG = "#e9ecef"
_RULE = "#d0d7de"
_CELL_BORDER = "#555555"
_FONT = "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
_BODY_STYLE = (f"margin:0;padding:16px;background:#ffffff;color:{_INK};{_FONT};font-size:15px;"
               "line-height:1.5")
_WRAP_STYLE = "max-width:640px;margin:0 auto"
_P_STYLE = "margin:0 0 12px"
_HEADING_STYLE = "margin:16px 0 6px"
_LIST_STYLE = "margin:0 0 12px;padding-left:24px"
_TABLE_STYLE = "border-collapse:collapse;width:100%;margin:4px 0 12px;font-size:14px"
_TH_STYLE = (f"background:{_HEAD_BG};font-weight:700;text-align:center;"
             f"border:1px solid {_CELL_BORDER};padding:6px 8px")
_TD_STYLE = f"border:1px solid {_CELL_BORDER};padding:6px 8px;text-align:center"
_NARROW = "width:1%;white-space:nowrap;background:#ffffff"
_GROUP_TITLE_STYLE = "margin:12px 0 4px;font-size:13px;font-weight:600;color:#57606a"
#: A section title: a line of the template that ends with «:» and is at most this long, rendered.
MAX_HEADING_CHARS = 40
#: The characters that open a list item in the template. «-» does NOT: a line the tenant opened
#: with a dash stays a line with its dash (the owner's model, 2026-10-22).
LIST_BULLETS = ("•", "·")
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"'\[\]]+", re.IGNORECASE)


@dataclass(frozen=True)
class _Look:
    palette: "tuple[str, ...]"
    colors: "Mapping[str, str]"


def _palette(appearance: "Optional[EmailAppearance]") -> "tuple[str, ...]":
    accent = appearance.accent_color if appearance is not None else ""
    return ((accent,) + tuple(c for c in DEFAULT_PALETTE if c != accent)) if accent \
        else DEFAULT_PALETTE


def record_colors(record_lists: "Iterable[object]",
                  appearance: "Optional[EmailAppearance]" = None) -> "dict[str, str]":
    """``{disciplina value: colour}`` over the e-mail's lists of records, in order — each list's
    groups in the order of their ``turma``, each group's records in order. A value gets the next
    colour of the palette (the tenant's accent first, :data:`DEFAULT_PALETTE` cycled) the FIRST time
    it appears, and keeps it for the whole e-mail: the same discipline in another class group, or
    in another table, has the same colour. Deterministic: a function of the lists alone."""
    palette = _palette(appearance)
    out: "dict[str, str]" = {}
    for records in record_lists:
        for _value, group in _record_groups(as_records(records) or []):
            for r in group:
                d = _field(r, _COLOR_KEY)
                if d and d not in out:
                    out[d] = palette[len(out) % len(palette)]
    return out


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _text_html(text: str) -> str:
    """Plain text as HTML: escaped, every line break a ``<br>``."""
    return _esc(text.replace("\r\n", "\n").replace("\r", "\n")).replace("\n", "<br>\n")


def _linked(text: str) -> str:
    """The tenant's own text as HTML: escaped, every ``http(s)://`` URL a link to itself (a
    trailing punctuation mark is left outside). Nothing else becomes markup."""
    out: "list[str]" = []
    pos = 0
    for m in _URL_IN_TEXT.finditer(text):
        url = m.group(0).rstrip(".,;:!?)")
        out.append(_esc(text[pos:m.start()]))
        out.append(f'<a href="{_esc(url)}">{_esc(url)}</a>')
        pos = m.start() + len(url)
    out.append(_esc(text[pos:]))
    return "".join(out)


def _table(head: "Sequence[str]", rows: "Sequence[Sequence[tuple[str, str]]]") -> str:
    """``rows`` of ``(cell text, extra style)``; the text is escaped."""
    th = "".join(f'<th style="{_TH_STYLE}">{_esc(h)}</th>' for h in head)
    body = "".join(
        "<tr>" + "".join(f'<td style="{_TD_STYLE}{";" + extra if extra else ""}">{_esc(text)}</td>'
                         for text, extra in row) + "</tr>"
        for row in rows)
    return f'<table style="{_TABLE_STYLE}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def _header(key: str) -> str:
    """A record key as its column's header: «mês» → «Mês», «valor_hora» → «Valor hora»."""
    text = key.strip().replace("_", " ")
    return text[:1].upper() + text[1:]


def records_html(records: object, *, colors: "Optional[Mapping[str, str]]" = None) -> str:
    """A list of records as HTML TABLES — the generic renderer every table of an e-mail is drawn
    by. ``""`` for anything that is not a list of records.

    * One column per key, in the order the keys first appear; a column empty in every record of
      a table is left out (an hour nobody has is not a column).
    * With a ``turma`` key: ONE table per value, under its «Turma X» title, in the order of the
      value, and no ``turma`` column (the table IS the class group's).
    * With a ``disciplina`` key: that cell has the value's colour (``colors``, from
      :func:`record_colors`), the other cells are white and narrow, the discipline's wide.
    * Every value and every header is escaped."""
    recs = as_records(records)
    if recs is None:
        return ""
    colors = colors or {}
    out: "list[str]" = []
    for value, group in _record_groups(recs):
        keys: "list[str]" = []
        for r in group:
            keys += [k for k in r if k not in keys and _fold_key(k) != _GROUP_KEY]
        keys = [k for k in keys if any(r.get(k) for r in group)]
        colored = any(_fold_key(k) == _COLOR_KEY for k in keys)
        rows = []
        for r in group:
            row = []
            for k in keys:
                cell = r.get(k, "")
                if colored and _fold_key(k) == _COLOR_KEY:
                    row.append((cell, f"background:{colors.get(cell, '#ffffff')}"))
                else:
                    row.append((cell, _NARROW if colored else ""))
            rows.append(row)
        title = (f'<p style="{_GROUP_TITLE_STYLE}">{_esc(_group_title(value))}</p>'
                 if value else "")
        out.append(title + _table([_header(k) for k in keys], rows))
    return "".join(out)


def _aulas_html(value: str, context: EmailContext, look: _Look) -> "Optional[str]":
    """``[aulas]``: :func:`records_html` of :func:`_aulas_records` — the coordinator only PRODUCES
    the list; the tables are the generic renderer's."""
    records = _aulas_records(context.classes)
    if not records or records_text(records) != value:
        return None
    return records_html(records, colors=look.colors)


def _disciplinas_html(value: str, context: EmailContext, look: _Look) -> "Optional[str]":
    """``[disciplinas]``: a list, one discipline per item, in the text's order."""
    subjects = _subjects(context.classes)
    if not subjects or "\n".join(subjects) != value:
        return None
    items = "".join(f"<li>{_esc(s)}</li>" for s in subjects)
    return f'<ul style="{_LIST_STYLE}">{items}</ul>'


def _bonus_html(value: str, context: EmailContext, look: _Look) -> "Optional[str]":
    """``[valores_por_bonus]``: a list of PAIRS through :func:`records_html` — a two-column table
    (Faixa · Valor), the determined band carrying the text's own mark — then the response-rate
    condition the bands hang on."""
    est = context.estimate
    if est is None or not est.tiers or _bonus_value(est) != value:
        return None
    mark = _bonus_mark(est)
    pairs = [{"faixa": label, "valor": money + (mark if applied else "")}
             for label, money, applied in _bonus_rows(est)]
    return records_html(pairs) + "".join(f'<p style="{_P_STYLE}">{_esc(c)}</p>'
                                         for c in _bonus_condition(est))


#: The block forms: a marker ALONE on a line of the template draws its block — the classes as
#: tables, the disciplines as a list, the bands as a two-column table. A form answers ``None``
#: when the context does not rebuild the very value the text carries; the value is then text.
_BLOCK_FORMS: "Mapping[str, Callable[[str, EmailContext, _Look], Optional[str]]]" = (
    MappingProxyType({
        "aulas": _aulas_html,
        "disciplinas": _disciplinas_html,
        "valores_por_bonus": _bonus_html,
    }))
#: The markers that make an e-mail go out as HTML: every provider's marker — a persona's
#: specific data — and no generic one. DERIVED from :data:`FIELD_PROVIDERS`.
_DATA_MARKERS: "frozenset[str]" = frozenset(f for p in FIELD_PROVIDERS.values()
                                            for f in p.field_names)
#: The producers of a list of records, by marker — what the colours of an e-mail are counted over.
_RECORD_SOURCES: "Mapping[str, Callable[[EmailContext], list[dict[str, str]]]]" = (
    MappingProxyType({"aulas": lambda context: _aulas_records(context.classes)}))
#: Figures that are bold wherever they stand (2026-10-22: «ou texto» — a figure is not a table).
_BOLD_INLINE = frozenset({"total", "valor_por_aula"})


def _value_html(name: str, value: str, context: EmailContext) -> str:
    """A marker's value inside a line: escaped, line breaks as ``<br>``. A FIXED company tag is
    the tenant's own text, so its URLs become links like the template's. No other value's do — a
    FREE tag's value is what the conversation said (``free_tag_values``), not the tenant's."""
    if name in _BOLD_INLINE:
        return f"<strong>{_text_html(value)}</strong>"
    tags = context.custom_tags if isinstance(context.custom_tags, Mapping) else {}
    fixed = isinstance(tags.get(name), str) and bool(_custom_value(tags[name]))
    if name not in EMAIL_FIELDS and is_custom_tag_name(name) and fixed:
        return "<br>\n".join(_linked(ln) for ln in
                             value.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    return _text_html(value)


def _line_html(line: str, values: "Mapping[str, str]",
               context: EmailContext) -> "tuple[str, str]":
    """One line of the template — ``(html, text)``: the tenant's words escaped (URLs as links),
    each marker its value. ONE pass: a marker typed inside a value stays text."""
    html_parts: "list[str]" = []
    text_parts: "list[str]" = []
    pos = 0
    for m in _MARKER.finditer(line):
        html_parts.append(_linked(line[pos:m.start()]))
        text_parts.append(line[pos:m.start()])
        name = m.group(1)
        html_parts.append(_value_html(name, values[name], context))
        text_parts.append(values[name])
        pos = m.end()
    html_parts.append(_linked(line[pos:]))
    text_parts.append(line[pos:])
    return "".join(html_parts), "".join(text_parts)


def _body_html(body: str, values: "Mapping[str, str]", context: EmailContext, look: _Look) -> str:
    """The template's body as simple rich text — four rules, and nothing else of Markdown:

    * a blank line separates paragraphs (the lines of one paragraph are joined by ``<br>``);
    * a line opened by «•» or «·» is a list item (consecutive ones are one list); a line opened by
      «-» stays a line with its dash;
    * a line that ends with «:» and is at most :data:`MAX_HEADING_CHARS` characters, rendered, is a
      section title in bold;
    * an ``http(s)://`` URL in the tenant's text is a link.

    A data marker alone on its line is its block (:data:`_BLOCK_FORMS`). Everything is escaped."""
    out: "list[str]" = []
    para: "list[str]" = []
    items: "list[str]" = []

    def flush() -> None:
        if para:
            out.append(f'<p style="{_P_STYLE}">' + "<br>\n".join(para) + "</p>")
            para.clear()
        if items:
            out.append(f'<ul style="{_LIST_STYLE}">'
                       + "".join(f"<li>{it}</li>" for it in items) + "</ul>")
            items.clear()

    for line in body.split("\n"):
        stripped = line.strip()
        alone = _MARKER.fullmatch(stripped)
        if not stripped:
            flush()
            continue
        if alone and alone.group(1) in _BLOCK_FORMS:
            name = alone.group(1)
            drawn = _BLOCK_FORMS[name](values[name], context, look)
            if drawn is not None:
                flush()
                out.append(drawn)
                continue
        if stripped[0] in LIST_BULLETS:
            if para:
                flush()
            items.append(_line_html(stripped[1:].lstrip(), values, context)[0])
            continue
        if items:
            flush()
        rendered, text = _line_html(stripped, values, context)
        if text.strip().endswith(":") and len(text.strip()) <= MAX_HEADING_CHARS:
            flush()
            out.append(f'<p style="{_HEADING_STYLE}"><strong>{rendered}</strong></p>')
            continue
        para.append(rendered)
    flush()
    return "\n".join(out)


def _signature_html(appearance: "Optional[EmailAppearance]", context: EmailContext) -> str:
    """The tenant's signature block — ``""`` exactly when :func:`email_signature_text` is ``""``:
    the logo on the LEFT with a thin vertical rule, the lines on the right (the persona's name in
    bold, the department, the phone, the e-mail and the site as links), the social links below —
    each its icon when one is configured (an image with the network's name as ``alt``), else the
    name as a link. In a table, which every mail client lays out."""
    if appearance is None or not appearance.has_signature:
        return ""
    name = context.persona_name.strip() or context.tenant_name.strip()
    lines = [f"<strong>{_esc(name)}</strong>"] if name else []
    lines += [_esc(v) for v in (appearance.department, appearance.phone) if v]
    if appearance.email:
        lines.append(f'<a href="mailto:{_esc(appearance.email)}">{_esc(appearance.email)}</a>')
    if appearance.site:
        lines.append(f'<a href="{_esc(appearance.site)}">{_esc(appearance.site)}</a>')
    logo = ""
    rule = ""
    if appearance.logo_url:
        logo = (f'<td style="padding:0 12px 0 0;vertical-align:middle">'
                f'<img src="{_esc(appearance.logo_url)}" '
                f'alt="{_esc(appearance.sender_name or context.tenant_name.strip() or "logótipo")}" '
                'width="80" style="display:block;width:80px;max-width:80px;height:auto;border:0">'
                "</td>")
        rule = f"border-left:1px solid {_RULE};padding:0 0 0 12px;"
    cell = (f'<td style="{rule}vertical-align:middle;font-size:13px;line-height:1.5">'
            + "<br>\n".join(lines) + "</td>")
    links = []
    for lk in appearance.links:
        if lk.icon_url:
            inner = (f'<img src="{_esc(lk.icon_url)}" alt="{_esc(lk.label)}" width="18" '
                     'height="18" style="display:inline-block;width:18px;height:18px;border:0">')
        else:
            inner = _esc(lk.label)
        links.append(f'<a href="{_esc(lk.url)}">{inner}</a>')
    social = (f'<tr><td colspan="{2 if logo else 1}" style="padding:8px 0 0 0;font-size:13px">'
              + " &nbsp; ".join(links) + "</td></tr>") if links else ""
    return (f'<table style="border-collapse:collapse;margin:20px 0 0 0"><tbody><tr>{logo}{cell}'
            f"</tr>{social}</tbody></table>")


def render_email_html(subject: str, body: str, values: "Mapping[str, str]",
                      context: EmailContext, *,
                      appearance: "Optional[EmailAppearance]" = None) -> str:
    """The e-mail's HTML form — a whole document — or ``""`` when it has none.

    ``""`` unless the BODY uses a marker with an HTML form (a persona's data: the classes, the
    disciplines, the pay values, the total). A template of generic markers or company tags goes
    out as the text it always was. A data marker in the SUBJECT alone draws nothing either.

    The HTML is the SAME e-mail as the text :func:`render_email_forms` gives with the same
    ``values``, never another one:

    * one pass over the template, as the text render: a marker typed inside a value stays text;
    * the template's own text and every value are escaped (``html.escape``); the template's body
      is simple rich text (:func:`_body_html`: paragraphs, «•»/«·» lists, short «…:» titles, URLs
      as links) and nothing else of the tenant's becomes markup;
    * a table is drawn only from rows of ``context`` whose text IS that marker's value in
      ``values`` — the value the text part carries; otherwise the value is shown as text;
    * the styles are inline. The ONLY images are the logo and the social icons the tenant
      configured in its ``appearance`` (``http``/``https``, escaped, with ``alt``); nothing else
      is loaded — no style sheet, no script, no tracking pixel;
    * a header with the sender's name (the appearance's, else the tenant's) and, when the tenant
      configured one, its signature block — the same lines :func:`email_signature_text` adds to
      the text.

    Raises ``ValueError`` exactly when :func:`render_email` does (a marker with no value, a
    subject that spans lines): the caller never gets here with a ``missing``.
    """
    rendered_subject, _ = render_email(subject, body, values)
    body = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    used = [m.group(1) for m in _MARKER.finditer(body)]
    if not any(name in _DATA_MARKERS for name in used):
        return ""
    lists = [_RECORD_SOURCES[name](context) for name in dict.fromkeys(used)
             if name in _RECORD_SOURCES]
    look = _Look(palette=_palette(appearance), colors=record_colors(lists, appearance))
    accent = (appearance.accent_color if appearance is not None else "") or _NAVY
    sender = ((appearance.sender_name if appearance is not None else "")
              or context.tenant_name.strip())
    header = (f'<p style="margin:0 0 16px;padding:0 0 8px;border-bottom:2px solid {accent};'
              f'font-size:16px;font-weight:700;color:{_NAVY}">{_esc(sender)}</p>\n'
              if sender else "")
    return ("<!DOCTYPE html>\n"
            '<html lang="pt-BR">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{_esc(rendered_subject)}</title>\n</head>\n"
            f'<body style="{_BODY_STYLE}">\n<div style="{_WRAP_STYLE}">\n'
            f"{header}{_body_html(body, values, context, look)}\n"
            f"{_signature_html(appearance, context)}\n</div>\n</body>\n</html>\n")


def render_email_forms(subject: str, body: str, values: "Mapping[str, str]",
                       context: EmailContext, *,
                       appearance: "Optional[EmailAppearance]" = None
                       ) -> "tuple[str, str, str]":
    """``(subject, text, html)`` — the ONE place the two forms of an e-mail are joined.

    ``text`` is :func:`render_email`'s body and, when the e-mail goes out as HTML and the tenant
    configured a signature, a blank line and :func:`email_signature_text` — the same lines the
    HTML's signature block draws. It is what the requester is shown and confirms, and what
    :func:`email_digest` is taken of. ``html`` is :func:`render_email_html`, ``""`` for an e-mail
    with no data marker in its body (its ``text`` is then :func:`render_email`'s, byte for byte).
    """
    out_subject, text = render_email(subject, body, values)
    doc = render_email_html(subject, body, values, context, appearance=appearance)
    signature = email_signature_text(appearance, context) if doc else ""
    return out_subject, (f"{text}\n\n{signature}" if signature else text), doc


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
    "render_email", "render_email_html", "render_email_forms", "email_digest", "missing_question", "is_email_month", "month_words",
    "date_words", "CUSTOM_TAG_NAME", "MAX_CUSTOM_TAG_CHARS", "MAX_CUSTOM_TAGS",
    "CUSTOM_TAG_SOURCE", "CUSTOM_TAG_REMOVED", "is_custom_tag_name", "custom_tag_problems",
    "normalise_custom_tags", "parse_custom_tags", "CUSTOM_TAG_FREE_SOURCE",
    "CUSTOM_TAG_FREE_MISSING", "MAX_CUSTOM_TAG_HINT_CHARS", "free_tags", "free_value",
    "free_value_problems", "custom_tag_hint_problems", "normalise_custom_tag_hints",
    "parse_custom_tag_hints",
    "EmailAppearance", "SocialLink", "APPEARANCE_FIELDS", "APPEARANCE_LINK_FIELDS",
    "APPEARANCE_URL_SCHEMES", "MAX_SOCIAL_LINKS", "DEFAULT_PALETTE", "LIST_BULLETS",
    "MAX_HEADING_CHARS", "normalise_email_appearance", "parse_email_appearance",
    "email_signature_text", "record_colors", "records_html", "records_text", "as_records",
    "MAX_RECORDS",
]
