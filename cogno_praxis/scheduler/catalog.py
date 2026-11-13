"""The CATALOG (services + products) for the scheduler vertical.

The tenant's offerings as STRUCTURED data: the single source is ``schedule_config["catalog"]``
(the tenant row the host already carries — no new table, no migration). A :class:`CatalogItem`
is a *described* thing with a ``kind``:

* a **service** (``kind="service"``) — a name, a DURATION (minutes, a positive multiple of 30),
  a value (optional), and WHO performs it (``all_hosts`` or a non-empty ``host_ids``, MANDATORY);
* a **product** (``kind="product"``) — a name and a value, **never** a duration or a professional,
  and **never** booked.

Two doors write the catalog, both only ADMIN of the tenant, both through ONE validator
(:func:`validate_catalog`): the structured screen (a list of items, professionals already chosen
by ``host_id``) and the IMPORT-by-text door (:func:`parse_catalog_block`, "paste the block" —
explicit ``SERVIÇOS:`` / ``PRODUTOS:`` sections, a line outside a section is invalid). The import
door resolves a professional's NAME to a ``host_id`` through the ONE agenda name-checker
(:mod:`cogno_praxis.scheduler.names`), so a name the booking path could not resolve is a name
this will not accept either; two namesakes are told apart by the SAME label the roster prints
(:func:`cogno_praxis.scheduler.names.host_label`).

**Read-only against the agenda in this slice.** ``duration_minutes`` is carried so the catalog is
complete and a later change books by it; the engine does not yet book by it. The only agenda-side rule here is
the PRODUCT guard (a product id is never scheduled — in :mod:`cogno_praxis.scheduler.service`).

WHY ``kind`` IS EXPLICIT (owner, 12/11): never "a missing duration means product". A service that
lost its duration would slip silently to a product (carrier-absent → stricter is the house rule),
so a service with no duration is INVALID, not a product.

VALUES use the ONE reader, :mod:`cogno_praxis.declared_values` — the grammar the nets and the
backstops use to ground a configured price, so ``R$ 90,00`` written here and ``R$ 90`` in a reply
are the same value. Durations read through the same reader's unit grammar (``60 min``, ``2 horas``).
No text of the tenant's ever reaches a log; the two events carry COUNTS only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Sequence

from cogno_praxis.declared_values import value_keys
from cogno_praxis.scheduler.names import _fold, host_candidates, host_label
from cogno_praxis.scheduler.store import Host

log = logging.getLogger(__name__)

KIND_SERVICE = "service"
KIND_PRODUCT = "product"

#: A service's duration must be a POSITIVE multiple of this many minutes (owner decision (b)/(c),
#: 12/11). Carried as a named constant so no path accepts a 20-minute service by accident.
DURATION_GRANULARITY_MIN = 30

#: Decision (c), CLOSED by the owner (12/11): price/duration is **per SERVICE**, with a LIST of
#: who performs it — NOT per professional. ``host_ids`` names WHO; it is not a price axis.
SERVICE_PRICE_PER_PROFESSIONAL = False

#: Upper bound on catalog size — a tenant's rules are not a database. Past it the whole block is
#: refused (the strict direction), never silently truncated to an arbitrary subset.
MAX_ITEMS = 128

#: The IMPORT-door spellings that mean "every schedulable professional", folded.
_ALL_PROFESSIONALS = frozenset({"todos", "todas", "all", "qualquer",
                                "todos os profissionais", "todas as profissionais"})

#: Section headers for the paste door (accent/case-insensitive, optional parenthetical legend).
_SERVICES_HEADER_RE = re.compile(r"^\s*servi[cç]os\b.*$", re.IGNORECASE)
_PRODUCTS_HEADER_RE = re.compile(r"^\s*produtos?\b.*$", re.IGNORECASE)
#: A catalog line is a bullet; a non-bullet, non-header, non-blank line is OUT OF SECTION.
_BULLET_RE = re.compile(r"^\s*[-*•]\s+(?P<body>.+?)\s*$")


# ── the closed reason vocabulary, fixed by TYPE ─────────────────────────────────────────
REASON_OUT_OF_SECTION = "fora_de_seccao"                 # a line before any SERVIÇOS:/PRODUTOS:
REASON_FORMAT = "formato"                                # wrong field count / empty name
REASON_VALUE = "valor"                                   # a value was written but is unreadable
REASON_SERVICE_NO_DURATION = "servico_sem_duracao"
REASON_DURATION_NOT_MULTIPLE = "duracao_nao_multipla_30"
REASON_NO_PROFESSIONAL = "sem_quem_faz"
REASON_PROFESSIONAL_NOT_FOUND = "profissional_nao_encontrado"
REASON_HOMONYM = "homonimo"                              # 2+ matches, told apart by label
REASON_HOMONYMS_INDISTINCT = "homonimos_indistinguiveis"  # 2+ with the SAME label → screen
REASON_PRODUCT_WITH_DURATION = "produto_com_duracao"
REASON_PRODUCT_WITH_PROFESSIONAL = "produto_com_profissional"
REASON_DUPLICATE = "item_duplicado"
REASON_TOO_MANY = "itens_a_mais"                         # more than MAX_ITEMS: the batch is refused whole

#: Roles that see the team report. A GUEST (the client) never does — not the report, not the
#: count: the report is for whoever wrote the catalog.
_TEAM_ROLES = frozenset({"ADMIN", "SUPERVISOR", "EMPLOYEE", "SECRETARY"})

_REASON_PHRASE = {
    REASON_OUT_OF_SECTION: "linha fora de qualquer secção (use SERVIÇOS: ou PRODUTOS:)",
    REASON_FORMAT: "formato inválido",
    REASON_VALUE: "valor ilegível",
    REASON_SERVICE_NO_DURATION: "serviço sem duração",
    REASON_DURATION_NOT_MULTIPLE: f"duração não é múltipla de {DURATION_GRANULARITY_MIN} min",
    REASON_NO_PROFESSIONAL: "sem quem faz (indique profissionais ou «todos»)",
    REASON_PROFESSIONAL_NOT_FOUND: "profissional não encontrado",
    REASON_HOMONYM: "homónimo",
    REASON_HOMONYMS_INDISTINCT: "homónimos indistinguíveis por texto — escolha no ecrã",
    REASON_PRODUCT_WITH_DURATION: "produto não tem duração",
    REASON_PRODUCT_WITH_PROFESSIONAL: "produto não tem profissionais",
    REASON_DUPLICATE: "item duplicado",
    REASON_TOO_MANY: f"itens a mais (o máximo é {MAX_ITEMS}) — nada foi gravado",
}
_PROFESSIONAL_REASONS = frozenset({REASON_PROFESSIONAL_NOT_FOUND})


@dataclass(frozen=True)
class CatalogItem:
    """One offered thing. ``kind`` is EXPLICIT (service|product). For a product,
    ``duration_minutes`` is 0 and ``all_hosts``/``host_ids`` are empty by construction."""

    item_id: str
    kind: str
    name: str
    description: str = ""
    value_text: str = ""
    duration_minutes: int = 0
    all_hosts: bool = False
    host_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_service(self) -> bool:
        return self.kind == KIND_SERVICE

    @property
    def is_product(self) -> bool:
        return self.kind == KIND_PRODUCT


@dataclass(frozen=True)
class DraftItem:
    """What a door hands the shared validator BEFORE resolution: the fields as the door has them.

    The screen door fills ``duration_minutes`` and (``all_hosts`` / ``host_ids``) — professionals
    already chosen by id. The import door fills ``duration_text`` and ``who_raw`` — raw cells the
    validator reads through the unit grammar and the name-checker. ``line_no`` is the line in the
    pasted block (0 for the screen door, which reports per index)."""

    kind: str
    name: str
    description: str = ""
    value_text: str = ""
    duration_text: str = ""
    duration_minutes: Optional[int] = None
    who_raw: Optional[str] = None
    all_hosts: Optional[bool] = None
    host_ids: Optional[tuple[str, ...]] = None
    line_no: int = 0


@dataclass(frozen=True)
class InvalidLine:
    """One line/item that could not become a :class:`CatalogItem`: its number (import door) or
    index (screen door), a closed reason, the attempted name/professional, and — for a homonym —
    the labels to write instead."""

    line_no: int
    reason: str
    name: str = ""
    labels: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CatalogParse:
    """The outcome of validating a batch of drafts: the valid items AND the invalid lines."""

    items: tuple[CatalogItem, ...] = field(default_factory=tuple)
    invalid: tuple[InvalidLine, ...] = field(default_factory=tuple)

    @property
    def services(self) -> "tuple[CatalogItem, ...]":
        return tuple(i for i in self.items if i.is_service)

    @property
    def products(self) -> "tuple[CatalogItem, ...]":
        return tuple(i for i in self.items if i.is_product)

    @property
    def refused(self) -> bool:
        """The batch must NOT replace the stored catalog: it was refused whole (more than
        :data:`MAX_ITEMS`), or not one item of it is valid while some line was written (a broken
        paste — a missing header, every line out of section — must not wipe the catalog the team
        has). An intentionally EMPTY batch (nothing written at all) is not refused: that is how the
        screen clears the catalog."""
        if any(i.reason == REASON_TOO_MANY for i in self.invalid):
            return True
        return not self.items and bool(self.invalid)


def item_id_for(kind: str, name: str) -> str:
    """A STABLE id from (kind, folded name): a re-import of the same catalog keeps the ids, so a
    booking made against a service id still points at the same service after the team pastes the
    block again. ``service:coloracao`` / ``product:shampoo_reparador``."""
    slug = re.sub(r"[^a-z0-9]+", "_", _fold(name)).strip("_") or kind
    return f"{kind}:{slug}"


def _duration_minutes(text: str) -> Optional[int]:
    """Minutes from a duration phrase through the declared-values unit grammar: ``60 min`` → 60,
    ``2 horas`` → 120, ``1 h 30 min`` → 90 (EVERY hour and minute unit of the phrase is added up —
    reading only the first one stored «1 h 30 min» as a 60-minute service). None when no
    hour/minute unit is present, and None for a half written in words («1 hora e meia»): the
    reader does not count it, and a duration that silently loses half an hour is worse than one
    the team is asked to rewrite. Only hours and minutes — a service duration is not days or
    weeks."""
    if re.search(r"\bmei[ao]\b", _fold(text or "")):
        return None
    total = Decimal("0")
    seen = False
    for k in value_keys(text):
        if k[0] == "unit" and k[2] in ("h", "min"):
            value = k[1] if isinstance(k[1], Decimal) else Decimal(str(k[1]))
            total += value * 60 if k[2] == "h" else value
            seen = True
    if not seen or total <= 0 or total != total.to_integral_value():
        return None
    return int(total)


def _money_decimal(value_text: str) -> Optional[Decimal]:
    """The first MONEY amount in ``value_text`` as a Decimal, via the one declared-values reader.
    None when the text names no money."""
    for k in value_keys(value_text):
        if k[0] == "money":
            return k[1] if isinstance(k[1], Decimal) else Decimal(str(k[1]))
    return None


#: Currency symbols the declared-values reader accepts, longest first so ``US$`` is not read as
#: ``$``. Used only to REFUSE a mixed-currency total (the amount itself is the reader's job).
_CURRENCY_SYMBOLS = ("R$", "US$", "€", "$")


def _currency_of(value_text: str) -> str:
    """The currency symbol a value literal carries, BRL (``R$``) assumed when none is written —
    the house currency. Used to refuse summing two currencies, never to invent an amount."""
    folded = value_text or ""
    for sym in _CURRENCY_SYMBOLS:
        if sym in folded:
            return sym
    return "R$"


def _resolve_names(who_raw: str, hosts: Sequence[Host]) -> "tuple[Optional[tuple[str, ...]], str, str, tuple[str, ...]]":
    """The IMPORT door's professionals cell → ``(host_ids, "", "", ())`` on success, else
    ``(None, reason, attempted_name, labels)``.

    ``todos`` (and its spellings) → ``all_hosts`` (returned as the sentinel ``()`` with no reason;
    the caller sets ``all_hosts=True``). Otherwise each comma-separated name must resolve, through
    the shared matcher, to EXACTLY ONE schedulable professional. 0 → not found. 2+ → homonyms:
    told apart by :func:`host_label`, so the reason carries the labels to write; two that share a
    label (same name AND role) cannot be told apart by text → ``homonimos_indistinguiveis`` (the
    screen chooses by id). Never invented, never the first of two."""
    field_text = (who_raw or "").strip()
    if not field_text:
        return None, REASON_NO_PROFESSIONAL, "", ()
    ids_out: list[str] = []
    for name in (n.strip() for n in field_text.split(",")):
        if not name:
            return None, REASON_NO_PROFESSIONAL, "", ()
        cands = host_candidates(name, list(hosts), by_role=False)
        if len(cands) == 0:
            return None, REASON_PROFESSIONAL_NOT_FOUND, name, ()
        if len(cands) > 1:
            labels = tuple(host_label(h) for h in cands)
            if len(set(labels)) < len(labels):
                return None, REASON_HOMONYMS_INDISTINCT, name, ()
            return None, REASON_HOMONYM, name, labels
        if cands[0].host_id not in ids_out:
            ids_out.append(cands[0].host_id)
    return tuple(ids_out), "", "", ()


def _validate_one(draft: DraftItem, hosts: Sequence[Host]
                  ) -> "tuple[Optional[CatalogItem], str, str, tuple[str, ...]]":
    """One draft → ``(item, "", "", ())`` or ``(None, reason, name, labels)``. The shared per-type
    rule both doors run through: value optional (unreadable-when-present → invalid); service needs
    a duration (positive multiple of 30) and someone to perform it; product forbids both."""
    kind = draft.kind
    if kind not in (KIND_SERVICE, KIND_PRODUCT) or not draft.name.strip():
        return None, REASON_FORMAT, "", ()
    name = draft.name.strip()

    # Value: optional in both. Present-but-unreadable is invalid; absent is "no value published".
    value_text = (draft.value_text or "").strip()
    if value_text and _money_decimal(value_text) is None:
        return None, REASON_VALUE, "", ()

    if kind == KIND_PRODUCT:
        has_duration = bool((draft.duration_text or "").strip()) or bool(draft.duration_minutes)
        if has_duration:
            return None, REASON_PRODUCT_WITH_DURATION, "", ()
        if draft.all_hosts or draft.host_ids or (draft.who_raw or "").strip():
            return None, REASON_PRODUCT_WITH_PROFESSIONAL, "", ()
        return (CatalogItem(item_id=item_id_for(kind, name), kind=kind, name=name,
                            description=(draft.description or "").strip(), value_text=value_text),
                "", "", ())

    # service — duration
    if draft.duration_minutes is not None:
        minutes: Optional[int] = draft.duration_minutes
    elif (draft.duration_text or "").strip():
        minutes = _duration_minutes(draft.duration_text)
        if minutes is None:
            return None, REASON_DURATION_NOT_MULTIPLE, "", ()
    else:
        return None, REASON_SERVICE_NO_DURATION, "", ()
    if minutes is None or minutes <= 0 or minutes % DURATION_GRANULARITY_MIN != 0:
        return None, REASON_DURATION_NOT_MULTIPLE, "", ()

    # service — who performs it (mandatory)
    all_hosts = bool(draft.all_hosts)
    host_ids: tuple[str, ...] = tuple(draft.host_ids or ())
    if draft.who_raw is not None and not all_hosts and not host_ids:
        if _fold((draft.who_raw or "").strip()) in _ALL_PROFESSIONALS:
            all_hosts = True
        else:
            ids, reason, who, labels = _resolve_names(draft.who_raw, hosts)
            if ids is None:
                return None, reason, who, labels
            host_ids = ids
    if not all_hosts and not host_ids:
        return None, REASON_NO_PROFESSIONAL, "", ()
    if host_ids:
        # The screen door hands ids directly — each must be a schedulable professional (
        # the catalog only REFERS ids that already exist; it never creates a professional).
        known = {h.host_id for h in hosts}
        missing = [hid for hid in host_ids if hid not in known]
        if missing:
            return None, REASON_PROFESSIONAL_NOT_FOUND, missing[0], ()
    return (CatalogItem(item_id=item_id_for(kind, name), kind=kind, name=name,
                        description=(draft.description or "").strip(), value_text=value_text,
                        duration_minutes=int(minutes), all_hosts=all_hosts, host_ids=host_ids),
            "", "", ())


def validate_catalog(drafts: Sequence[DraftItem], hosts: Sequence[Host]) -> CatalogParse:
    """The ONE validator both doors run (the screen and the paste): every draft validated by its
    type, then a (kind, folded name) DUPLICATE invalidates EVERY item that shares it (never "first
    wins" — two prices for one name is a configuration to fix, not a coin to flip). More than
    :data:`MAX_ITEMS` refuses the whole batch, diagnostics kept. Does NOT log — the caller records
    ``catalog_saved`` at the write site (:func:`record_catalog_saved`)."""
    valid: "list[tuple[int, CatalogItem]]" = []
    invalid: list[InvalidLine] = []
    for idx, draft in enumerate(drafts):
        line_no = draft.line_no or (idx + 1)
        item, reason, who, labels = _validate_one(draft, hosts)
        if item is None:
            invalid.append(InvalidLine(line_no=line_no, reason=reason, name=who, labels=labels))
        else:
            valid.append((line_no, item))
    counts: "dict[tuple[str, str], int]" = {}
    for _, it in valid:
        counts[(it.kind, _fold(it.name))] = counts.get((it.kind, _fold(it.name)), 0) + 1
    dups = {k for k, n in counts.items() if n > 1}
    if dups:
        kept: "list[tuple[int, CatalogItem]]" = []
        for line_no, it in valid:
            if (it.kind, _fold(it.name)) in dups:
                invalid.append(InvalidLine(line_no=line_no, reason=REASON_DUPLICATE, name=it.name))
            else:
                kept.append((line_no, it))
        valid = kept
    items = tuple(it for _, it in valid)
    if len(items) > MAX_ITEMS:
        # Refused WHOLE, and SAID: an empty, reasonless result read as «0 valid, 0 invalid», and a
        # door that stored it wiped the catalog the team had. The doors read ``refused`` and keep
        # the stored catalog.
        items = ()
        invalid.append(InvalidLine(line_no=0, reason=REASON_TOO_MANY))
    invalid.sort(key=lambda i: i.line_no)
    return CatalogParse(items=items, invalid=tuple(invalid))


def parse_catalog_block(text: str, hosts: Sequence[Host]) -> CatalogParse:
    """The IMPORT door ("paste the block"): read explicit ``SERVIÇOS:`` / ``PRODUTOS:`` sections
    into drafts and run them through :func:`validate_catalog`. A bullet line BEFORE any section
    header is OUT OF SECTION (invalid and counted). A non-bullet line ends nothing — only a header
    switches the section; a bullet is a line, anything else that is not blank is reported out of
    section if no section is open, else ignored as the legend/prose the team wrote."""
    drafts: list[DraftItem] = []
    pre_section_invalid: list[InvalidLine] = []
    section: Optional[str] = None
    for line_no, ln in enumerate((text or "").splitlines(), start=1):
        if not ln.strip():
            continue
        if _SERVICES_HEADER_RE.match(ln):
            section = KIND_SERVICE
            continue
        if _PRODUCTS_HEADER_RE.match(ln):
            section = KIND_PRODUCT
            continue
        m = _BULLET_RE.match(ln)
        if m is None:
            continue
        if section is None:
            pre_section_invalid.append(InvalidLine(line_no=line_no, reason=REASON_OUT_OF_SECTION))
            continue
        drafts.append(_draft_from_line(section, m.group("body"), line_no))
    parse = validate_catalog(drafts, hosts)
    if pre_section_invalid:
        merged = sorted([*parse.invalid, *pre_section_invalid], key=lambda i: i.line_no)
        parse = CatalogParse(items=parse.items, invalid=tuple(merged))
    return parse


def draft_from_item_dict(d: dict, index: int) -> DraftItem:
    """A STRUCTURED screen-door item ``{id?, kind, name, description?, value_text?,
    duration_minutes?, all_hosts?|host_ids?}`` → a draft for the SHARED validator. ``index`` is
    the item's position (reported back as the invalid line). The client's ``id`` is ignored — a
    stable id is derived from (kind, name), so the panel cannot forge one."""
    if not isinstance(d, dict):
        return DraftItem(kind="", name="", line_no=index)
    dur = d.get("duration_minutes")
    minutes: Optional[int] = None
    if dur is not None and dur != "":
        try:
            minutes = int(dur)
        except (TypeError, ValueError):
            minutes = None
    host_ids = (tuple(str(h) for h in d["host_ids"])
                if isinstance(d.get("host_ids"), list) else None)
    return DraftItem(
        kind=str(d.get("kind", "")), name=str(d.get("name", "")),
        description=str(d.get("description", "")), value_text=str(d.get("value_text", "")),
        duration_minutes=minutes,
        all_hosts=bool(d["all_hosts"]) if "all_hosts" in d else None,
        host_ids=host_ids, line_no=index)


def validate_item_dicts(dicts: Sequence[dict], hosts: Sequence[Host]) -> CatalogParse:
    """The SCREEN door: a list of structured item dicts → the shared validation. Mirror of
    :func:`parse_catalog_block` for the text door, through the SAME :func:`validate_catalog`."""
    return validate_catalog([draft_from_item_dict(d, i) for i, d in enumerate(dicts)], hosts)


def invalid_to_dict(inv: InvalidLine) -> dict:
    """One invalid line → the structured report entry for the admin API: ``index`` (the
    item/line it was), the closed ``reason``, the attempted ``name``, and a ``detail`` for a
    homonym (the labels to write instead)."""
    out: dict = {"index": inv.line_no, "reason": inv.reason}
    if inv.name:
        out["name"] = inv.name
    if inv.reason == REASON_HOMONYM and inv.labels:
        out["detail"] = "escreva um destes: " + ", ".join(f'"{lbl}"' for lbl in inv.labels)
    return out


def _draft_from_line(kind: str, body: str, line_no: int) -> DraftItem:
    """One pasted line into a draft. Services: ``name | duration | value | professionals`` (value
    may be blank). Products: ``name | value`` (value may be blank). A wrong field count becomes a
    FORMAT reason in the validator (the draft carries an empty name / flags that fail there)."""
    parts = [p.strip() for p in body.split("|")]
    if kind == KIND_SERVICE:
        if len(parts) != 4:
            return DraftItem(kind=kind, name="", line_no=line_no)   # → REASON_FORMAT
        name, dur, val, who = parts
        return DraftItem(kind=kind, name=name, value_text=val, duration_text=dur,
                         who_raw=who, line_no=line_no)
    if len(parts) != 2:
        return DraftItem(kind=kind, name="", line_no=line_no)       # → REASON_FORMAT
    name, val = parts
    return DraftItem(kind=kind, name=name, value_text=val, line_no=line_no)


# ── serialization: the single source is schedule_config["catalog"] ───────────────────────────
def item_to_dict(it: CatalogItem) -> dict:
    """A :class:`CatalogItem` → the dict stored in ``schedule_config["catalog"]`` (a product omits
    the service-only keys so the stored shape says what it is)."""
    out: dict = {"id": it.item_id, "kind": it.kind, "name": it.name}
    if it.description:
        out["description"] = it.description
    if it.value_text:
        out["value_text"] = it.value_text
    if it.is_service:
        out["duration_minutes"] = it.duration_minutes
        if it.all_hosts:
            out["all_hosts"] = True
        else:
            out["host_ids"] = list(it.host_ids)
    return out


def catalog_to_dicts(items: Sequence[CatalogItem]) -> list[dict]:
    """The valid items → the list stored under ``schedule_config["catalog"]``."""
    return [item_to_dict(it) for it in items]


def catalog_from_config(schedule_config: Optional[dict]) -> "tuple[CatalogItem, ...]":
    """Read the stored catalog from a tenant's ``schedule_config`` (the ``catalog`` key). Absent/
    malformed → empty (the SECRETARY behaves exactly as with no catalog). Defensive: a stored item
    that cannot be read is skipped, never crashes the turn."""
    if not isinstance(schedule_config, dict):
        return ()
    raw = schedule_config.get("catalog")
    if not isinstance(raw, list):
        return ()
    out: list[CatalogItem] = []
    for d in raw:
        if not isinstance(d, dict):
            continue
        kind = str(d.get("kind", ""))
        name = str(d.get("name", ""))
        if kind not in (KIND_SERVICE, KIND_PRODUCT) or not name:
            continue
        out.append(CatalogItem(
            item_id=str(d.get("id") or d.get("item_id") or item_id_for(kind, name)),
            kind=kind, name=name,
            description=str(d.get("description", "")), value_text=str(d.get("value_text", "")),
            duration_minutes=int(d.get("duration_minutes", 0) or 0),
            all_hosts=bool(d.get("all_hosts", False)),
            host_ids=tuple(str(h) for h in d.get("host_ids", ()) if h)))
    return tuple(out)


# ── reading: list_services (two lists) + the one line definition ─────────────────────────────
def _who_names(it: CatalogItem, hosts: Sequence[Host]) -> "list[str]":
    """The CURRENT names of the professionals who perform a service, read from the directory at
    render time (a rename shows the new name; a professional with no schedule is dropped). For
    ``all_hosts`` → everyone with a schedule."""
    by_id = {h.host_id: h for h in hosts}
    if it.all_hosts:
        return [h.name for h in hosts]
    return [by_id[hid].name for hid in it.host_ids if hid in by_id]


def unoffered_count(items: Sequence[CatalogItem], hosts: Sequence[Host]) -> int:
    """How many SERVICES have nobody to perform them NOW (every listed professional lost their
    schedule, and not ``all_hosts`` — or ``all_hosts`` with an empty roster). The ``catalog_unoffered``
    count."""
    n = 0
    for it in items:
        if not it.is_service:
            continue
        if not _who_names(it, hosts):
            n += 1
    return n


#: The per-item ceiling on a catalog DESCRIPTION as ``list_services`` PRINTS it (the
#: ``PERSONA_TEXT_CEILINGS`` mould — a NAMED number). The description is the business's own text
#: (third-party) that the Secretary describes the item by; this clips it ON OUTPUT so one item
#: cannot flood the result. It is NOT a new IMPORT refusal — the thirteen reasons and the screen
#: mirror are untouched; today only ``MAX_ITEMS`` has a ceiling. The text reaches the model only as
#: the RESULT of ``list_services``, inside the core's tool-result fence that already neutralises the
#: item NAME — never in the system block, never in a log.
DESCRIPTION_PRINT_CEILING = 280


def clip_description(description: str) -> str:
    """The item's description as ``list_services`` PRINTS it: whitespace AND line breaks collapsed
    to single spaces (so a description never fabricates a line of its own), cut at the last word
    boundary before :data:`DESCRIPTION_PRINT_CEILING` and ended with "…" (the whole result, "…"
    included, fits the ceiling). Square brackets print as parentheses. ``""`` when there is none.
    """
    desc = " ".join((description or "").split()).strip()
    # Square brackets are the id spelling of the grid line (``_grid_with_id``): a description prints
    # them as parentheses, so its line never carries — nor ends in — something read as an item id.
    desc = desc.replace("[", "(").replace("]", ")")
    if len(desc) <= DESCRIPTION_PRINT_CEILING:
        return desc
    cut = desc[:DESCRIPTION_PRINT_CEILING]
    boundary = cut.rfind(" ")
    # One word longer than the ceiling: drop one more character so the "…" stays inside it.
    return (cut[:boundary] if boundary > 0 else cut[:-1]).rstrip() + "…"


def _with_description(line: str, description: str) -> str:
    """The item line, plus — when the item HAS a description — a SECOND, INDENTED line
    (``  descrição: <texto>``) right after it, OUTSIDE the ``name — duration — value — who`` grid
    the voice and the nets read, and indented so it is never taken for another item. An item WITHOUT
    a description renders the line byte-for-byte as before."""
    desc = clip_description(description)
    return f"{line}\n  descrição: {desc}" if desc else line


def format_service_line(it: CatalogItem, hosts: Sequence[Host]) -> str:
    """The ONE spelling of a service line (the duration-aware booking reads its FIRST line too).
    ``name — 2 h — R$ 260,00 — Ana, Bia``; a missing value → "sem valor publicado"; ``all_hosts`` →
    "todos". A description, when the item has one, follows on a second indented line (``format``
    grid untouched)."""
    value = it.value_text or "sem valor publicado"
    who = "todos" if it.all_hosts else ", ".join(_who_names(it, hosts))
    return _with_description(
        f"{it.name} — {format_duration(it.duration_minutes)} — {value} — {who}", it.description)


def format_product_line(it: CatalogItem) -> str:
    """The ONE spelling of a product line: ``name — R$ 60,00`` (or "sem valor publicado"), with the
    item's description on a second indented line when it has one."""
    return _with_description(f"{it.name} — {it.value_text or 'sem valor publicado'}", it.description)


def format_duration(minutes: int) -> str:
    """A duration spoken: ``60`` → ``1 h``, ``90`` → ``1 h 30 min``, ``30`` → ``30 min``."""
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h} h {m} min"
    if h:
        return f"{h} h"
    return f"{m} min"


def _grid_with_id(block: str, item_id: str) -> str:
    """Append the item's id as ``[item_id]`` to its GRID line (the first) — the SAME spelling the
    refusals print (``service.py``: «name [item_id]»), so the model passes the id it has already
    seen in a refusal. Added HERE and never in ``format_service_line`` (which carries no id, so an
    id never reaches a line shared with the duration booking): the id lives only in the
    ``list_services`` OUTPUT, on the grid line, BEFORE any description line."""
    head, sep, rest = block.partition("\n")
    return f"{head} [{item_id}]{sep}{rest}"


def render_service_catalog(items: Sequence[CatalogItem], hosts: Sequence[Host]) -> str:
    """The two SEPARATE lists for ``list_services``: services with duration+value+who (those with
    nobody to perform them now are dropped) then products with value, each with its id in brackets
    (the spelling the refusals use) so the model can pass it as ``service_id``, and a description on
    an indented second line when the item has one. Empty catalog → the "nothing configured" line.
    Logs ``catalog_unoffered`` (count only)."""
    services = [it for it in items if it.is_service and _who_names(it, hosts)]
    products = [it for it in items if it.is_product]
    n_unoffered = unoffered_count(items, hosts)
    if n_unoffered:
        log.debug("stage=scheduler event=catalog_unoffered n=%d", n_unoffered)
    if not services and not products:
        return "No services or products are configured."
    blocks: list[str] = []
    if services:
        blocks.append("Serviços:\n" + "\n".join(
            f"- {_grid_with_id(format_service_line(s, hosts), s.item_id)}" for s in services))
    if products:
        blocks.append("Produtos:\n" + "\n".join(
            f"- {_grid_with_id(format_product_line(p), p.item_id)}" for p in products))
    return "\n\n".join(blocks)


#: The SERVICES step for the secretary's system prompt. FIXED prose — it carries no tenant text
#: (names, prices and descriptions are third-party text and reach the model only through the
#: prompt guard, as the RESULT of ``list_services``), so a catalog edit never moves the digest and
#: the two goldens are one value: "no catalog" (byte for byte as before) and "catalog present".
SERVICES_SYSTEM_BLOCK = """## Services, Products & Prices
This business keeps a structured catalog of the SERVICES and PRODUCTS it offers. Read it with
`list_services` whenever the user asks what exists or what something costs ("quais serviços?",
"o que vocês fazem?", "quanto custa X?", "quanto fica A + B?") — never recite a service or a
price from memory and never invent one; `list_services` returns the real names, durations,
prices and who performs each, and sums a total for you in code when asked.

When you CHECK availability or BOOK a service, NAME it: pass its `service_id` (the id
`list_services` prints in brackets) to `check_availability` and `book_appointment`. The booking
then occupies that service's WHOLE duration, and only a professional who performs it can take
it. With a catalog present, a booking that names no service is refused and the services are
offered — so read `list_services` first and pass the `service_id` the client chose (unless the
business offers a single service).

A PRODUCT is DESCRIBED and PRICED, never scheduled and never sold. You explain a product and
give its price when asked, but you do NOT take an order, reserve stock, take payment, or promise
delivery — a purchase is made in person. If the user wants to buy ("quero comprar", "separa um
pra mim", "como pago?"), say warmly that the purchase is made on the spot; you do not complete
sales and there is no "salesperson" to transfer to."""


def services_system_block(schedule_config: "Optional[dict]") -> str:
    """The ``{{SERVICES_CATALOG}}`` fill for the secretary's ``system.txt`` — the fixed
    :data:`SERVICES_SYSTEM_BLOCK` wrapped as its own section when the tenant HAS a catalog, and
    ``""`` when it does not. The catalog is an opt-in surface: an empty fill leaves the rendered
    system prompt byte for byte what it was before this feature, so a tenant with no catalog
    moves no digest. Called host-side (``cogno_host.identity.host_blocks``)."""
    if not catalog_from_config(schedule_config):
        return ""
    return "\n" + SERVICES_SYSTEM_BLOCK + "\n"


def render_catalog_report(parse: CatalogParse, hosts: Sequence[Host], role: str) -> str:
    """The team's diagnostic of a write, or ``""`` for a GUEST or a clean batch. Each invalid
    line: its number, the closed reason, and — for a professional reason — the attempted name and
    the roster; for a homonym, the labels to write instead."""
    if (role or "").upper() not in _TEAM_ROLES or not parse.invalid:
        return ""
    roster = ", ".join(host_label(h) for h in hosts) or "(ninguém)"
    out = [f"[Catálogo — equipe] {len(parse.items)} item(ns) válido(s), "
           f"{len(parse.invalid)} linha(s) inválida(s):"]
    for inv in parse.invalid:
        phrase = _REASON_PHRASE.get(inv.reason, inv.reason)
        if inv.reason == REASON_HOMONYM and inv.labels:
            opts = ", ".join(f'"{lbl}"' for lbl in inv.labels)
            out.append(f"- linha {inv.line_no}: {phrase}: {inv.name} casa com "
                       f"{len(inv.labels)} — escreva um destes: {opts}")
        elif inv.reason in _PROFESSIONAL_REASONS:
            named = f": {inv.name}" if inv.name else ""
            out.append(f"- linha {inv.line_no}: {phrase}{named} — "
                       f"cadastrados com agenda: {roster}")
        else:
            out.append(f"- linha {inv.line_no}: {phrase}")
    return "\n".join(out)


# ── total on demand — summed in CODE, never by the model ────────────────────────────────
class CatalogTotalError(ValueError):
    """A total was asked for and cannot be summed honestly (an item without a value, two
    currencies). Recoverable: the caller relays the reason, never a made-up number."""


def resolve_item_token(token: str, items: Sequence[CatalogItem]) -> Optional[CatalogItem]:
    """A free token (an id OR a folded name) → the one catalog item it names, or None when it
    matches nobody or TWO. Lets the total be asked by NAME ("corte + manicure") without the model
    carrying ids, while never guessing between two same-named items."""
    tok = (token or "").strip()
    if not tok:
        return None
    by_id = {it.item_id: it for it in items}
    if tok in by_id:
        return by_id[tok]
    folded = _fold(tok)
    named = [it for it in items if _fold(it.name) == folded]
    return named[0] if len(named) == 1 else None


def catalog_total(item_ids: Sequence[str], items: Sequence[CatalogItem]
                  ) -> "tuple[Decimal, str, list[tuple[str, str]]]":
    """Sum the values of the named items IN CODE: ``(total, currency, [(name, value_text)])``.

    Each value read by the ONE declared-values reader, as ``Decimal``, BRL by default. NEVER a sum
    the model did (the judge rejects a total with no operation in view). An unknown id, an item
    with no value, or TWO currencies → :class:`CatalogTotalError` with the reason — never a guess.
    """
    by_id = {it.item_id: it for it in items}
    total = Decimal("0")
    currency = ""
    lines: "list[tuple[str, str]]" = []
    for iid in item_ids:
        it = by_id.get(iid)
        if it is None:
            raise CatalogTotalError(f"não conheço o item {iid!r}")
        if not it.value_text:
            raise CatalogTotalError(f"não tenho o valor de {it.name}")
        amount = _money_decimal(it.value_text)
        if amount is None:
            raise CatalogTotalError(f"não tenho o valor de {it.name}")
        cur = _currency_of(it.value_text)
        if currency and cur != currency:
            raise CatalogTotalError("os valores estão em moedas diferentes — não posso somar")
        currency = cur
        total += amount
        lines.append((it.name, it.value_text))
    return total, currency or "R$", lines


# ── the write event, owned here so the LOGGING page documents it ────────────────────────
def record_catalog_saved(door: str, valid: int, invalid: int) -> None:
    """Emit ``catalog_saved door=<ecrã|import> valid=<n> invalid=<n>`` — the ONE write event, a
    COUNT only, called by either door after it writes. ``door`` is a fixed token (``ecrã`` /
    ``import``), never tenant text."""
    token = "ecrã" if str(door).startswith("ecr") else "import"
    log.info("stage=scheduler event=catalog_saved door=%s valid=%d invalid=%d",
             token, int(valid), int(invalid))
