"""A SEED of classes for the coordinator, read from a FILE, for ONE tenant (the rehearsal's).

The coordinator's classes come from the tenant's Google spreadsheets: the host passes an OAuth
token, and without one the subprocess serves an EMPTY in-memory store. A rehearsal tenant has no
Google grant, so its coordinator has no classes and nothing on that path can be rehearsed. The
scheduler solved the same problem for deterministic harnesses with ``COGNO_SCHEDULER_SEED``.

The coordinator's seed is a FILE (``COGNO_COORDINATOR_SEED_FILE``), and it carries the tenant it
belongs to. **The guard is the point.** The subprocess inherits the box's environment — a seed
variable set on the box reaches the coordinator of EVERY tenant — so the file is applied only
when the tenant the host names for this turn (``COGNO_COORDINATOR_TENANT``) is the file's own.
Absent, blank, or another tenant: the store is the empty one of today. And never over a Google
token: a tenant with a grant reads its spreadsheets, whatever the box says. Only the spreadsheet
ids the tenant's own rules name are seeded.

The names are invented.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import pytest

from cogno_praxis.coordinator import server as srv

_SID = "1EnsAioAuLaS-SintEtIcAs-0000000000001"
_OUTRA = "1OutRaPlAnIlHa-SintEtIcA-000000000002"
_RULES = (f"SPREADSHEETS:\nTurma Alfa = {_SID}\n"
          'TAB_SCHEDULE: "Secretaria"\nRANGE_SCHEDULE: "A4:E200"\n'
          'COLUMN_DATE: "Data"\nCOLUMN_PROFESSOR: "Professor"\nCOLUMN_SUBJECT: "Disciplina"\n'
          'FIXED_COLUMNS: "Data, Dia"\nFREE_SLOT_LABELS: "Livre"\nSKIP_LABELS: "Feriado"\n')
_TENANT = "tenant-ensaio-0001"
_GRID = [[""] * 5, [""] * 5, [""] * 5, ["Data", "Dia", "Professor", "Disciplina", "Sala"],
         ["22/10/2026", "Qui", "Docente Alfa", "Bancos de Dados", "101"],
         ["29/10/2026", "Qui", "Docente Alfa", "Bancos de Dados", "101"],
         ["30/10/2026", "Sex", "Docente Beta", "Redes", "102"]]


def _ficheiro(tmp_path, *, tenant=_TENANT, sheets=None) -> str:
    p = tmp_path / "aulas.json"
    p.write_text(json.dumps({"tenant": tenant,
                             "sheets": sheets if sheets is not None
                             else {_SID: {"Secretaria": _GRID}}}), encoding="utf-8")
    return str(p)


@pytest.fixture
def _env(monkeypatch):
    for name in ("COGNO_COORDINATOR_GOOGLE_TOKEN", "COGNO_COORDINATOR_SEED_FILE",
                 "COGNO_COORDINATOR_TENANT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COGNO_COORDINATOR_RULES", _RULES)
    monkeypatch.setenv("COGNO_COORDINATOR_TODAY", "2026-10-21")
    return monkeypatch


def _aulas(prof: str = "Docente Alfa") -> "list[str]":
    svc = srv._demo_service()
    return [e.date_str for e in svc.get_professor_schedule(professor=prof, role="SUPERVISOR",
                                                                 identity_label="Coordenação")]


# ── the seed ─────────────────────────────────────────────────────────────────────────────────

def test_GEMEO_o_ficheiro_do_tenant_que_corre_e_a_planilha_dele(_env, tmp_path):
    """On the tree before: no seed exists — the store is empty and the professor has no class."""
    _env.setenv("COGNO_COORDINATOR_SEED_FILE", _ficheiro(tmp_path))
    _env.setenv("COGNO_COORDINATOR_TENANT", _TENANT)
    assert _aulas() == ["22/10/2026", "29/10/2026"]
    assert _aulas("Docente Beta") == ["30/10/2026"]


def test_GEMEO_aplicada_diz_quantas_planilhas_e_linhas_nunca_o_tenant(_env, tmp_path, caplog):
    _env.setenv("COGNO_COORDINATOR_SEED_FILE", _ficheiro(tmp_path))
    _env.setenv("COGNO_COORDINATOR_TENANT", _TENANT)
    with caplog.at_level(logging.DEBUG, logger="cogno_praxis.coordinator.seed"):
        srv._demo_service()
    linhas = [r.getMessage() for r in caplog.records]
    assert linhas == [f"stage=coordinator event=seed_applied sheets=1 rows={len(_GRID)}"]
    assert _TENANT not in " ".join(linhas) and _SID not in " ".join(linhas)


# ── the guard ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("quem", [None, "", "   ", "outro-tenant", _TENANT.upper()])
def test_o_ficheiro_de_outro_tenant_ou_de_ninguem_nao_se_aplica(_env, tmp_path, quem):
    _env.setenv("COGNO_COORDINATOR_SEED_FILE", _ficheiro(tmp_path))
    if quem is not None:
        _env.setenv("COGNO_COORDINATOR_TENANT", quem)
    assert _aulas() == []


def test_sem_tenant_nomeado_o_ficheiro_nem_se_le(_env, tmp_path, caplog):
    """A host that names no tenant costs no read: an unreadable file says nothing."""
    p = tmp_path / "aulas.json"
    p.write_text("não é json", encoding="utf-8")
    _env.setenv("COGNO_COORDINATOR_SEED_FILE", str(p))
    with caplog.at_level(logging.DEBUG, logger="cogno_praxis.coordinator.seed"):
        assert _aulas() == []
    assert [r.getMessage() for r in caplog.records] == [
        "stage=coordinator event=seed_skipped reason=no_tenant"]


def test_um_ficheiro_sem_tenant_nao_e_de_ninguem(_env, tmp_path):
    _env.setenv("COGNO_COORDINATOR_SEED_FILE", _ficheiro(tmp_path, tenant=""))
    _env.setenv("COGNO_COORDINATOR_TENANT", "")
    assert _aulas() == []


def test_nunca_por_cima_de_um_token_do_google(_env, tmp_path):
    """A tenant with a grant reads its spreadsheets: the seed is not even read."""
    lidos = []
    _env.setattr(srv, "apply_seed", lambda *a, **k: lidos.append(1) or 0, raising=False)
    _env.setenv("COGNO_COORDINATOR_SEED_FILE", _ficheiro(tmp_path))
    _env.setenv("COGNO_COORDINATOR_TENANT", _TENANT)
    _env.setenv("COGNO_COORDINATOR_GOOGLE_TOKEN", "ya29.token-de-teste")
    svc = srv._demo_service()
    assert type(svc.store).__name__ == "GoogleSheetsStore" and lidos == []


def test_so_as_planilhas_que_as_regras_do_tenant_nomeiam(_env, tmp_path, caplog):
    """A sheet the rules do not name never enters the store — not even where nothing reads it."""
    _env.setenv("COGNO_COORDINATOR_SEED_FILE", _ficheiro(
        tmp_path, sheets={_OUTRA: {"Secretaria": _GRID}}))
    _env.setenv("COGNO_COORDINATOR_TENANT", _TENANT)
    with caplog.at_level(logging.DEBUG, logger="cogno_praxis.coordinator.seed"):
        svc = srv._demo_service()
    assert svc.store.read_range(_OUTRA, "Secretaria", "A1:E200") == []
    assert [r.getMessage() for r in caplog.records] == [
        "stage=coordinator event=seed_skipped reason=no_sheet_for_rules"]
    assert _aulas() == []


@pytest.mark.parametrize("conteudo", ["", "não é json", "[]", '{"tenant": 1, "sheets": {}}',
                                      json.dumps({"tenant": _TENANT, "sheets": []}),
                                      json.dumps({"tenant": _TENANT,
                                                  "sheets": {_SID: {"Secretaria": "x"}}}),
                                      json.dumps({"tenant": _TENANT,
                                                  "sheets": {_SID: {"Secretaria": [["a", 1]]}}})])
def test_um_ficheiro_ilegivel_e_o_vazio_de_hoje_e_avisa_sem_o_conteudo(_env, tmp_path, caplog,
                                                                    conteudo):
    p = tmp_path / "aulas.json"
    p.write_text(conteudo, encoding="utf-8")
    _env.setenv("COGNO_COORDINATOR_SEED_FILE", str(p))
    _env.setenv("COGNO_COORDINATOR_TENANT", _TENANT)
    with caplog.at_level(logging.WARNING, logger="cogno_praxis.coordinator.seed"):
        assert _aulas() == []
    linhas = [r.getMessage() for r in caplog.records]
    assert len(linhas) == 1 and linhas[0].startswith("stage=coordinator event=seed_unreadable ")
    assert _TENANT not in linhas[0] and str(p) not in linhas[0]


def test_um_ficheiro_que_nao_existe_e_o_vazio_de_hoje(_env, tmp_path):
    _env.setenv("COGNO_COORDINATOR_SEED_FILE", str(tmp_path / "nao-existe.json"))
    _env.setenv("COGNO_COORDINATOR_TENANT", _TENANT)
    assert _aulas() == []


# ── the controls ─────────────────────────────────────────────────────────────────────────────

def test_CONTROLO_sem_a_variavel_o_servico_e_o_de_hoje(_env):
    """Both worlds: no seed file → the empty in-memory store with the header-only grid."""
    svc = srv._demo_service()
    assert type(svc.store).__name__ == "InMemorySpreadsheetStore"
    assert _aulas() == []
    assert svc._today() == date(2026, 10, 21)


def test_CONTROLO_a_grelha_dada_a_mao_e_lida_como_a_semente_a_daria():
    """The service reads a hand-placed grid of the same shape — the seed adds a way in, not a
    second reader."""
    from cogno_praxis.coordinator import (CoordinatorConfig, CoordinatorService,
                                          InMemorySpreadsheetStore)
    store = InMemorySpreadsheetStore()
    store.put(_SID, "Secretaria", _GRID)
    svc = CoordinatorService(store, CoordinatorConfig(_RULES), today=lambda: date(2026, 10, 21))
    assert [e.date_str for e in svc.get_professor_schedule(
        professor="Docente Alfa", role="SUPERVISOR", identity_label="Coordenação")] == \
        ["22/10/2026", "29/10/2026"]
