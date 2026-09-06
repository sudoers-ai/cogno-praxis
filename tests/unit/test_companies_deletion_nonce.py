"""The second step of ``company_delete`` carries something the first step PRODUCED.

Every assertion here is about the STORE, never about a message: a gate that answers "NOT
REMOVED" while the row leaves is the defect these tests exist to catch, and the wording is the
half a refactor is allowed to change.

The defect they close, measured 2026-09-06 through EGO → host write policy → this vertical:
``delete`` decided by comparing ``confirm_company_id`` with the row's own ``company_id``, and
``company_id`` is the tool's required FIRST argument (and derived from the accent-folded name,
so it is guessable from the company's name alone). One call with the id on both ends removed
the company with nothing proposed to anybody.
"""

from __future__ import annotations

import pytest

from cogno_praxis.companies import (
    CompanyService,
    InMemoryCompanyStore,
    InMemoryConfirmationStore,
    confirmation_subject,
    mint_token,
)
from cogno_praxis.companies.confirmations import DEFAULT_CONFIRMATION_TTL_S


def _svc(clock=None) -> CompanyService:
    svc = CompanyService(InMemoryCompanyStore(),
                         **({"clock": clock} if clock else {}))
    svc.register("Acme", identity_id="e1")
    svc.register("Initech", identity_id="e1")
    return svc


def _ids(svc: CompanyService) -> "list[str]":
    return [c.company_id for c in svc.list_companies()]


# ── twin 1: the id on both ends is NOT a confirmation ────────────────────────────────────
def test_the_id_on_both_ends_removes_nothing():
    """The measured hole, as its own twin. The assertion is ZERO WRITES."""
    svc = _svc()
    out = svc.delete("acme", identity_id="e1", role="ADMIN", confirm_token="acme")
    assert out.removed is None
    assert _ids(svc) == ["acme", "initech"]

    # and neither is the company NAME, the CNPJ, or the id of the other company — every value
    # a caller holds before the first call has to fail the same way.
    for guess in ("Acme", "acme", "initech", "", "   ", "11222333000181"):
        assert svc.delete("acme", identity_id="e1", role="ADMIN",
                          confirm_token=guess).removed is None
    assert _ids(svc) == ["acme", "initech"]


def test_a_call_with_no_token_proposes_and_writes_nothing():
    svc = _svc()
    out = svc.delete("acme", identity_id="e1", role="ADMIN")
    assert out.removed is None and out.proposal is not None
    assert out.proposal.company.company_id == "acme"
    assert _ids(svc) == ["acme", "initech"]


# ── twin 2: first step mints, second step spends ─────────────────────────────────────────
def test_the_token_the_proposal_minted_does_commit():
    """A gate that also blocked the confirmed path would protect the row by breaking it."""
    svc = _svc()
    proposal = svc.delete("acme", identity_id="e1", role="ADMIN").proposal
    assert proposal is not None
    gone = svc.delete("acme", identity_id="e1", role="ADMIN",
                      confirm_token=proposal.confirm_token).removed
    assert gone is not None and gone.company_id == "acme"
    assert _ids(svc) == ["initech"]


def test_the_token_is_not_derivable_from_anything_the_caller_holds():
    """It is a SECRET, not a rendering of the row.

    Three checks, and the third is the one that actually separates a secret from a rendering:
    the token is LONG, it is not any value the caller already holds, and **two proposals over
    identical inputs differ**. A derivation of the row would repeat.

    NOT a substring sweep over the ids, and that correction was made by measurement rather
    than by taste: the first version of this test asserted `"e1" not in token`, and this PR's
    own CI failed on `c6CotqpBJR65Las7EZRcR581Te1ycz_U` — a random 32-character token contains
    a given two-character string by chance roughly once in thirty runs. **An assertion that
    fails on a CORRECT implementation is a worse defect than the one it guards**, and it costs
    nothing here: the mutation this test exists for (`fresh = row.company_id`) is killed by the
    length check and by the equality check, both deterministic.
    """
    svc = _svc()
    proposal = svc.delete("acme", identity_id="e1", role="ADMIN").proposal
    assert proposal is not None
    token = proposal.confirm_token
    assert len(token) >= 24
    assert token not in ("acme", "Acme", "e1", "initech", "")
    # two proposals for the SAME company are two different tokens
    second = svc.delete("acme", identity_id="e1", role="ADMIN").proposal
    assert second is not None and second.confirm_token != token


# ── twin 3: a token from ANOTHER call is refused ─────────────────────────────────────────
def test_a_token_minted_for_another_company_is_refused():
    svc = _svc()
    other = svc.delete("initech", identity_id="e1", role="ADMIN").proposal
    assert other is not None
    assert svc.delete("acme", identity_id="e1", role="ADMIN",
                      confirm_token=other.confirm_token).removed is None
    assert _ids(svc) == ["acme", "initech"]
    # and it still works for the company it WAS minted for — the refusal is binding, not damage
    assert svc.delete("initech", identity_id="e1", role="ADMIN",
                      confirm_token=other.confirm_token).removed is not None


def test_a_token_minted_for_another_identity_is_refused():
    """An oversight role may write to a company it did not register — so the pair is
    ``(identity, company)``, and a token is not transferable between people."""
    svc = _svc()
    mine = svc.delete("acme", identity_id="e1", role="ADMIN").proposal
    assert mine is not None
    assert svc.delete("acme", identity_id="e2", role="ADMIN",
                      confirm_token=mine.confirm_token).removed is None
    assert _ids(svc) == ["acme", "initech"]


def test_a_freshly_minted_token_from_nowhere_is_refused():
    svc = _svc()
    assert svc.delete("acme", identity_id="e1", role="ADMIN",
                      confirm_token=mint_token()).removed is None
    assert _ids(svc) == ["acme", "initech"]


# ── twin 4: a token is spent ONCE ────────────────────────────────────────────────────────
def test_a_token_cannot_be_spent_twice():
    """Otherwise it is a shared secret with a nice name, not a nonce."""
    svc = _svc()
    proposal = svc.delete("acme", identity_id="e1", role="ADMIN").proposal
    assert proposal is not None
    assert svc.delete("acme", identity_id="e1", role="ADMIN",
                      confirm_token=proposal.confirm_token).removed is not None
    svc.register("Acme", identity_id="e1")          # the same key comes back
    assert _ids(svc) == ["acme", "initech"]
    assert svc.delete("acme", identity_id="e1", role="ADMIN",
                      confirm_token=proposal.confirm_token).removed is None
    assert _ids(svc) == ["acme", "initech"]


def test_a_refused_attempt_does_not_burn_a_pending_confirmation():
    """A wrong guess must not cost the contact the confirmation they are about to give."""
    svc = _svc()
    proposal = svc.delete("acme", identity_id="e1", role="ADMIN").proposal
    assert proposal is not None
    svc.delete("initech", identity_id="e1", role="ADMIN",
               confirm_token=proposal.confirm_token)        # wrong subject
    assert svc.delete("acme", identity_id="e1", role="ADMIN",
                      confirm_token=proposal.confirm_token).removed is not None


# ── the clock: expiry refuses, and the window is the HOST's ──────────────────────────────
def test_an_expired_token_is_refused_and_a_new_one_is_offered():
    now = [1_000.0]
    svc = _svc(clock=lambda: now[0])
    proposal = svc.delete("acme", identity_id="e1", role="ADMIN").proposal
    assert proposal is not None
    now[0] += DEFAULT_CONFIRMATION_TTL_S + 1
    out = svc.delete("acme", identity_id="e1", role="ADMIN",
                     confirm_token=proposal.confirm_token)
    assert out.removed is None and out.proposal is not None
    assert _ids(svc) == ["acme", "initech"]
    # the answer to a stale confirmation is a FRESH proposal, not a dead end
    assert svc.delete("acme", identity_id="e1", role="ADMIN",
                      confirm_token=out.proposal.confirm_token).removed is not None


def test_a_slow_contact_inside_the_hosts_own_window_still_confirms():
    """The failure a nonce must not introduce: a removal without confirmation traded for a
    confirmation that never arrives. 1800 s is `Host(confirm_ttl_s=1800.0)` — the window in
    which an affirmative may release a held confirmation at all — so the vertical is never the
    binding constraint."""
    assert DEFAULT_CONFIRMATION_TTL_S == 1800.0
    now = [1_000.0]
    svc = _svc(clock=lambda: now[0])
    proposal = svc.delete("acme", identity_id="e1", role="ADMIN").proposal
    assert proposal is not None
    now[0] += 1_799.0                                   # 29 min 59 s later: still theirs
    assert svc.delete("acme", identity_id="e1", role="ADMIN",
                      confirm_token=proposal.confirm_token).removed is not None


# ── the port ─────────────────────────────────────────────────────────────────────────────
def test_ownership_is_decided_before_a_token_is_ever_minted():
    """A token must never become a way around `_mine_or_refuse`."""
    from cogno_praxis.companies import CompanyError

    tokens = InMemoryConfirmationStore()
    svc = CompanyService(InMemoryCompanyStore(), confirmations=tokens)
    svc.register("Acme", identity_id="e1")
    with pytest.raises(CompanyError):
        svc.delete("acme", identity_id="stranger", role="GUEST")
    assert tokens.tokens == {}


def test_the_subject_binds_both_halves_and_cannot_be_forged_by_a_separator():
    a = confirmation_subject("e1\x1facme", "")
    b = confirmation_subject("e1", "acme")
    assert a != b


def test_the_store_is_a_port_the_host_can_replace():
    """The in-memory default is right for a test and WRONG for production — the vertical is a
    subprocess per turn, so the two halves of a removal run in two processes."""
    tokens = InMemoryConfirmationStore()
    svc = CompanyService(InMemoryCompanyStore(), confirmations=tokens)
    svc.register("Acme", identity_id="e1")
    proposal = svc.delete("acme", identity_id="e1", role="ADMIN").proposal
    assert proposal is not None
    assert list(tokens.tokens) == [proposal.confirm_token]
    subject, _expires = tokens.tokens[proposal.confirm_token]
    assert subject == confirmation_subject("e1", "acme")

    svc.delete("acme", identity_id="e1", role="ADMIN", confirm_token=proposal.confirm_token)
    assert tokens.tokens == {}                          # spent is gone


def test_purge_drops_only_the_expired():
    tokens = InMemoryConfirmationStore()
    tokens.issue("s", "old", expires_at=10.0)
    tokens.issue("s", "new", expires_at=100.0)
    assert tokens.purge_expired(now=50.0) == 1
    assert list(tokens.tokens) == ["new"]
