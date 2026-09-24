"""The praxis folds remove ACCENTS, never LETTERS — a replica of the host's ``textfold.fold``.

The scheduler's and the bookkeeper's folds used to be ``NFKD(lower).encode("ascii", "ignore")``.
That does not strip an accent: it deletes every character outside ASCII. «Łucja Øverby» folded to
``"ucja verby"``, and a professional whose name is written in a non-Latin script folded to ``""``
— the same empty key as every other one, so no such name could be found by name. In the
bookkeeper, a search term made only of such characters («€») folded to ``""``, and an empty term
matches EVERY entry.

The contract is the ecosystem's ONE fold, ``cogno_host.textfold.fold`` as it stands since
``cogno-host`` #1004 and its ``casefold`` follow-up: NFKD → combining marks removed →
``casefold``, in that order (idempotent over all of Unicode; «Straße» and «Strasse» are one). ``cogno-host`` pins these copies against its own over 100 000 strings; this
file pins the definition and what it changes here. Every name below is INVENTED.
"""

import random
import string
import unicodedata

import pytest

from cogno_praxis.bookkeeper.engine import NOT_SEARCHABLE, BookkeeperError
from cogno_praxis.bookkeeper.engine import _fold as bookkeeper_fold
from cogno_praxis.bookkeeper.engine import matches_query
from cogno_praxis.bookkeeper.service import BookkeeperService
from cogno_praxis.coordinator.service import _norm as coordinator_norm
from cogno_praxis.scheduler.service import SchedulerService, _fold, _host_tokens
from cogno_praxis.scheduler.store import Host, InMemoryAppointmentStore


def _host_base_fold(s: str) -> str:
    """``cogno_host.textfold.fold`` with no flags, written out — the replica must match it."""
    folded = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in folded if not unicodedata.combining(ch)).casefold()


CATALOGUE = ["Dra. Valquíria de Assunção Bragantim", "João da Conceição Araújo",
             "Łucja Øverby", "Graça Straße", "李小龙", "王菲", "Joao Conceicao Pimentel",
             "𝐄𝐬𝐭𝐞𝐯𝐚𝐨 𝐐𝐮𝐢𝐫𝐢𝐧𝐨"]


def _svc():
    hosts = {f"h{i}": Host(f"h{i}", n, "") for i, n in enumerate(CATALOGUE)}
    return SchedulerService(InMemoryAppointmentStore(hosts=hosts))


def _names(svc, text):
    return sorted(h.name for h in svc._host_candidates(text))


# ── the definition ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fold,host_equivalent", [
    (_fold, _host_base_fold),
    (bookkeeper_fold, _host_base_fold),
    # the coordinator's `_norm` was already in the host's order; it strips the ends as well:
    # `textfold.fold(t, strip=True)`. Pinned here so it cannot drift away from the other two.
    (coordinator_norm, lambda t: _host_base_fold(t).strip()),
], ids=["scheduler", "bookkeeper", "coordinator"])
def test_the_fold_is_the_hosts_on_accents_ligatures_and_non_latin_letters(fold, host_equivalent):
    rng = random.Random(0)
    alphabet = "aeiouçãõáéíóúâêôàüñßøłİıﬁ ’-ÆæŒœ李王€–ᴬϒ℃𝐉𝐨𝓜" + string.ascii_letters
    corpus = ["".join(rng.choice(alphabet) for _ in range(rng.randint(1, 12)))
              for _ in range(20_000)] + ["", "ᴬ", "ϒ", "ẞ", "ΟΔΟΣ", "ΟΔΟΣ ΚΑΙ", "Ꭰꭰ", "  João  "]
    assert [fold(t) for t in corpus] == [host_equivalent(t) for t in corpus]


def test_the_fold_keeps_the_letters_and_removes_only_the_marks():
    assert _fold("João da Conceição") == "joao da conceicao"        # accents: gone, as before
    assert _fold("Łucja Øverby") == "łucja øverby"                   # was "ucja verby"
    assert _fold("李小龙") == "李小龙"                                  # was ""
    assert _fold("Straße") == "strasse"                              # casefold, as in the host
    assert _fold("ΟΔΟΣ") == "οδοσ"                                   # final sigma: no context
    assert _fold("𝐄𝐬𝐭𝐞𝐯𝐚𝐨") == "estevao"                             # NFKD first: lower-case


# ── what it changes in whose-agenda resolution ────────────────────────────────────────

@pytest.mark.parametrize("name", ["李小龙", "王菲"])
def test_a_name_in_a_non_latin_script_is_found_by_its_own_name(name):
    """Before: both keys were ``""`` and neither professional was reachable by name."""
    assert _names(_svc(), name) == [name]


def test_a_name_in_fancy_letters_is_found_by_the_plain_name():
    """A display name in mathematical bold letters — the shape many WhatsApp profiles have."""
    assert _names(_svc(), "estevao quirino") == ["𝐄𝐬𝐭𝐞𝐯𝐚𝐨 𝐐𝐮𝐢𝐫𝐢𝐧𝐨"]
    assert _names(_svc(), "Estêvão Quirino") == ["𝐄𝐬𝐭𝐞𝐯𝐚𝐨 𝐐𝐮𝐢𝐫𝐢𝐧𝐨"]


def test_a_letter_nfkd_does_not_decompose_stays_in_the_token():
    """``_host_tokens`` used to split on ``[^0-9a-z]``, which would cut «Łucja» to «ucja» even
    after the fold stopped deleting the «ł». It splits on non-word characters now."""
    assert _host_tokens("Łucja Øverby") == frozenset({"łucja", "øverby"})
    assert _names(_svc(), "Łucja") == ["Łucja Øverby"]


def test_sharp_s_behaves_exactly_as_in_the_host():
    """Parity with the host, which folds with ``casefold``: «Strasse» IS «Straße»."""
    assert _names(_svc(), "Straße") == ["Graça Straße"]
    assert _names(_svc(), "Strasse") == ["Graça Straße"]
    assert _names(_svc(), "GRAÇA STRASSE") == ["Graça Straße"]


def test_CONTROL_accents_omitted_resolve_exactly_as_before():
    svc = _svc()
    for query in ("Joao da Conceicao Araujo", "João da Conceição Araújo", "Joao Araujo",
                  "valquiria bragantim", "Dra. Valquíria"):
        assert len(_names(svc, query)) == 1, query


def test_INVERSE_an_accented_query_finds_a_label_stored_WITHOUT_accents():
    """The other direction of the same rule: the catalogue says «Joao Conceicao Pimentel» and
    the contact types «Joáo Pimentel». Both sides go through the fold, so the accent the CONTACT
    added costs nothing either."""
    assert _names(_svc(), "Joáo Pimentel") == ["Joao Conceicao Pimentel"]
    assert _names(_svc(), "Joáo Conceição Pimentel") == ["Joao Conceicao Pimentel"]


# ── the bookkeeper's keyword search ───────────────────────────────────────────────────

def _ledger():
    svc = BookkeeperService()
    for desc, amount in (("Aluguel março", 1200.0), ("Padaria Pão de Açúcar", 45.0),
                         ("Pagamento em € a fornecedor", 300.0), ("CAFÉ da manhã", 12.5)):
        svc.add_outcome(desc, amount, "u1")
    return svc


@pytest.mark.parametrize("term", ["€", "!!!", "–", " € $ ", "́"])
def test_a_term_with_no_letter_and_no_digit_is_REFUSED_with_the_reason(term):
    """Before: «€» folded to "" and the empty term matched EVERY entry — the whole ledger came
    back as the answer to a search for the euro sign. "Nothing found" would be the other silent
    failure. The answer is a refusal that says why, and nothing is searched."""
    with pytest.raises(BookkeeperError, match=NOT_SEARCHABLE):
        _ledger().search(term, "u1", "EMPLOYEE")


def test_a_removal_by_such_a_term_is_refused_the_same_way():
    with pytest.raises(BookkeeperError, match=NOT_SEARCHABLE):
        _ledger().remove_by_search("€", "u1")


def test_CONTROL_real_searches_answer_exactly_as_before():
    svc = _ledger()
    descs = lambda q: sorted(t["description"] for t in svc.search(q, "u1", "EMPLOYEE"))  # noqa: E731
    assert descs("pao de acucar") == ["Padaria Pão de Açúcar"]
    assert descs("cafe") == ["CAFÉ da manhã"]
    assert descs("março") == ["Aluguel março"]
    assert descs("45,00") == ["Padaria Pão de Açúcar"]
    assert descs("fornecedor") == ["Pagamento em € a fornecedor"]
    assert len(descs("")) == 4, "a BLANK term keeps its meaning: list everything"


def test_a_deleted_character_no_longer_invents_a_match():
    """«ßa» used to fold to "a" and match every entry with an «a» in it."""
    assert not matches_query("Casa", "ßa")
