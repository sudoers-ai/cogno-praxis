"""No log call of this package formats text somebody else wrote, or an identifier — the class,
by AST.

One WARNING of the coordinator carried two professors' names. ``LOGGING.md`` said so, and said
that four more carried a spreadsheet's id. Read by AST on ``5e7a452``, 12 of the package's 19
log calls formatted somebody's text or an identifier:

* 1 with two PEOPLE's names — the rows of the professors tab that share an address;
* 4 with a spreadsheet's ID, the name the tenant gave it and the ``repr`` of the store's
  exception — whose message embeds the request URL, and the id again;
* 3 more with what the TENANT typed — the name of a spreadsheet, of a tab and of two columns, a
  discipline, and the sentences of the persona's rules that state pay figures;
* 2 with an EXCEPTION's message — the holiday calendar's, and Postgres's, which quotes the row
  it tripped on;
* 1 with a SCOPE — a tenant's id and a contact's channel id;
* 1 with a tenant's name for a spreadsheet, next to the length of the value that was not an id.

Every value a log call formats is named by the ``key=`` in front of its placeholder
(``tests/unit/_log_calls.py`` refuses a message where one is not). ``LOGGING.md`` gives every
key ONE class — count, closed, type, digest, constant; there is no class for text — and
:data:`EXPRESSIONS` pins the expression each key is given. A new key, or a new expression under
an old key, fails here until somebody classifies it.

What the lines say at run time is the other file's:
``test_log_lines_carry_no_name_and_no_id.py``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import cogno_praxis
from cogno_praxis.logsafe import id_sha
from tests.unit import _log_calls as reader

PACKAGE = Path(cogno_praxis.__file__).parent
DOC = PACKAGE.parent / "LOGGING.md"

CALLS, STRANGERS = reader.package_calls(PACKAGE)

#: The classes a value may have. ``constant`` is for a key that only ever has a literal.
VALUE_CLASSES = ("count", "closed", "type", "digest")
CLASSES = VALUE_CLASSES + ("constant",)

#: What each key is GIVEN — the source of the argument, as ``ast.unparse`` writes it. A class
#: is a judgement about an expression, so the judgement is pinned to the expression it was
#: about.
_PINNED: "dict[str, set[str]]" = {
    # ── count ──
    "excerpts": {"sum((len(h.excerpts) for h in hints))"},
    "kept": {"kept"},
    "pairs": {"len(unsettled)"},
    "row": {"number"},
    "rows": {"rows"},
    "sheets": {"len(mine)"},
    "status": {"_http_status(exc)"},
    "value_len": {"len(value)"},
    # ── closed ──
    "action": {"f'SELECT scope,host_id,date,time,count(*) FROM appointments WHERE status IN "
               "({_ACTIVE_SQL_LIST}) GROUP BY 1,2,3,4 HAVING count(*)>1'"},
    "keys": {"','.join((h.key for h in hints))"},
    "missing": {"','.join((name for (name, idx) in (('hours', h_idx), ('subject', s_idx)) "
                "if idx is None))"},
    "reason": {"getattr(exc, 'sqlstate', None) or 'unknown'"},
    "tab": {"tab"},
    "var": {"TENANT_SMTP_ENV"},
    # ── type ──  (the shape is held below: `type(<name>).__name__`)
    "error": {"type(exc).__name__"},
    # ── digest ──  (the shape is held below: `id_sha(<anything>)`)
    "country_sha": {"id_sha(country)"},
    "scope_sha": {"id_sha(self._scope)"},
    "sheet_sha": {"id_sha(key)", "id_sha(sheet_key)"},
    "state_sha": {"id_sha(state) or '-'"},
}


def _as_this_python_writes_it(source: str) -> str:
    """``ast.unparse`` does not write an expression the same way on every Python: 3.10 gives
    ``for (s, v) in present.items()`` where 3.11 gives ``for s, v in present.items()``. A pin
    is the EXPRESSION, not one interpreter's spelling of it, so each is parsed and written back
    by the interpreter that is running — the same one that wrote the reader's side."""
    return ast.unparse(ast.parse(source, mode="eval"))


EXPRESSIONS: "dict[str, set[str]]" = {
    key: {_as_this_python_writes_it(source) for source in sources}
    for key, sources in _PINNED.items()}


def field_classes(text: str) -> "dict[str, str]":
    """``{key: class}`` from the fields table of ``LOGGING.md``. A row is
    ``| `key` | class | what |``, or ``| `key` in `logger` | class | what |`` for a key whose
    class differs in one logger (returned as ``key@logger``)."""
    out: "dict[str, str]" = {}
    for line in text.splitlines():
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip())]
        if len(cells) != 5 or cells[0] or cells[-1]:
            continue
        key = re.fullmatch(r"`(\w+)`(?: in `(cogno_praxis[\w.]*)`)?", cells[1])
        if not key or cells[2] not in CLASSES + ("text", "digest"):
            continue
        name = key.group(1) + (f"@{key.group(2)}" if key.group(2) else "")
        assert name not in out, f"{name} has two rows"
        out[name] = cells[2]
    return out


def _key(call: reader.LogCall, key: str, table: "dict[str, object]") -> str:
    scoped = f"{key}@{call.logger}"
    return scoped if scoped in table else key


def unclassified(calls: "list[reader.LogCall]", classes: "dict[str, str]",
                 expressions: "dict[str, set[str]]") -> "list[str]":
    """Every way a call's values escape the table — one line each; ``[]`` is the pass."""
    out: "list[str]" = []
    for call in calls:
        where = f"{call.module}:{call.lineno} event={call.event}"
        for key, _, source in call.values:
            cls = classes.get(_key(call, key, classes))
            if cls is None:
                out.append(f"{where}: {key}= has no class in LOGGING.md")
            elif cls not in VALUE_CLASSES:
                out.append(f"{where}: {key}= is classed {cls!r} and is given a value")
            if source not in expressions.get(_key(call, key, expressions), set()):
                out.append(f"{where}: {key}= is given {source!r}, which nobody classified")
            if cls == "type" and not re.fullmatch(r"type\(\w+\)\.__name__", source):
                out.append(f"{where}: {key}= is classed type and is given {source!r}")
            if cls == "digest" and not re.fullmatch(r"id_sha\([\w.]+\)( or '-')?", source):
                out.append(f"{where}: {key}= is classed digest and is given {source!r}")
        for key, _ in call.literals:
            if _key(call, key, classes) not in classes:
                out.append(f"{where}: {key}= has no class in LOGGING.md")
    return out


CLASSES_ON_THE_PAGE = field_classes(DOC.read_text(encoding="utf-8"))


# ── by AST: every value has a class, and no class is text ──────────────────────────────────

def test_every_value_a_log_call_formats_has_a_class():
    assert not STRANGERS, STRANGERS
    assert unclassified(CALLS, CLASSES_ON_THE_PAGE, EXPRESSIONS) == []


def test_no_key_is_classed_as_text():
    assert set(CLASSES_ON_THE_PAGE.values()) <= set(CLASSES)
    assert "text" not in CLASSES_ON_THE_PAGE.values()


def test_the_page_and_the_pins_list_the_keys_the_code_uses_and_no_other():
    used: "set[str]" = set()
    given: "set[str]" = set()
    for call in CALLS:
        used |= {_key(call, k, CLASSES_ON_THE_PAGE) for k in call.fields}
        given |= {_key(call, k, EXPRESSIONS) for k, _, _ in call.values}
    assert set(CLASSES_ON_THE_PAGE) == used
    assert set(EXPRESSIONS) == given
    constant = {k for k, cls in CLASSES_ON_THE_PAGE.items() if cls == "constant"}
    assert constant == used - given, "constant is for a key that never takes a value"


def test_every_pinned_expression_is_still_what_some_call_is_given():
    seen: "dict[str, set[str]]" = {}
    for call in CALLS:
        for key, _, source in call.values:
            seen.setdefault(_key(call, key, EXPRESSIONS), set()).add(source)
    assert seen == EXPRESSIONS


def test_no_line_carries_a_traceback():
    """A traceback says what the exception says. The package has none; one that arrives fails
    here until the page says why it may."""
    assert [call for call in CALLS if call.traceback] == []


def test_the_package_has_no_other_way_to_write_a_line():
    """A ``print``, a ``warnings.warn``, a write to a standard stream or a hand-formatted
    traceback is a log line this reader would never see."""
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                called = ast.unparse(node.func)
                if called in ("print", "warnings.warn", "warn", "pprint", "pprint.pprint") \
                        or called.startswith(("sys.stdout", "sys.stderr", "traceback.")):
                    found.append(f"{path.name}:{node.lineno} {called}")
    assert found == []


def test_the_tab_of_an_unreadable_sheet_is_one_of_four_words():
    """``sheet_unreadable`` is one log call in a helper, so ``tab=`` is a parameter there. What
    it may be is held at the CALLERS: each passes one of four literals of the module, never the
    name the tenant gave the tab."""
    tree = ast.parse((PACKAGE / "coordinator" / "service.py").read_text(encoding="utf-8"))
    passed = [node.args[0] for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == "_log_unreadable"]
    assert len(passed) == 4
    assert all(isinstance(arg, ast.Constant) for arg in passed)
    assert sorted(arg.value for arg in passed) == ["hours", "ibope", "professors", "schedule"]
    row = next(ln for ln in DOC.read_text(encoding="utf-8").splitlines()
               if "`sheet_unreadable`" in ln and ln.startswith("|"))
    assert "`tab=schedule\\|hours\\|ibope\\|professors`" in row


def test_the_digest_is_the_hosts_definition_and_not_a_second_one():
    """``id_sha`` is the first 12 hex characters of the SHA-256 of the value — what the
    reference host's ``scope_sha`` computes. The vector is that definition, written out."""
    import hashlib
    for value in ("tenant-7:contact-42", "Turma AA_01", "x"):
        assert id_sha(value) == hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    assert id_sha("tenant-7:contact-42") == "31c247c92321"
    assert id_sha("") == id_sha(None) == ""
    assert id_sha(7) == id_sha("7") and len(id_sha("x", length=8)) == 8
    assert "tenant-7" not in id_sha("tenant-7:contact-42")


# ── the controls of the AST half ───────────────────────────────────────────────────────────

def _planted(line: str) -> "list[reader.LogCall]":
    calls, strangers = reader.read(
        "import logging\n_log = logging.getLogger('cogno_praxis.coordinator.service')\n"
        f"{line}\n", "cogno_praxis.coordinator.service")
    assert not strangers
    return calls


def test_control_the_defect_under_a_better_name_is_caught():
    """``pairs=%d`` given the two names: the key is classified, the expression is not."""
    calls = _planted('_log.warning("stage=coordinator event=faculty_names_not_joined pairs=%s", '
                     '(a, b))')
    said = unclassified(calls, CLASSES_ON_THE_PAGE, EXPRESSIONS)
    assert len(said) == 1 and "nobody classified" in said[0]


def test_control_a_new_key_is_caught_twice():
    calls = _planted('_log.warning("stage=coordinator event=sheet_unreadable sheet_id=%s", sid)')
    said = unclassified(calls, CLASSES_ON_THE_PAGE, EXPRESSIONS)
    assert len(said) == 2 and "has no class" in said[0] and "nobody classified" in said[1]


def test_control_an_exception_message_is_not_a_type():
    calls = _planted('_log.warning("stage=coordinator event=sheet_unreadable error=%s", exc)')
    said = unclassified(calls, CLASSES_ON_THE_PAGE, EXPRESSIONS)
    assert len(said) == 2 and "classed type" in said[1]


def test_control_an_identifier_is_not_its_digest():
    calls = _planted('_log.warning("stage=coordinator event=sheet_unreadable sheet_sha=%s", '
                     'sheet_id)')
    said = unclassified(calls, CLASSES_ON_THE_PAGE, EXPRESSIONS)
    assert len(said) == 2 and "classed digest" in said[1]


def test_control_a_key_classed_as_text_is_caught():
    calls = _planted('_log.warning("stage=coordinator event=sheet_unreadable tab=%s", tab)')
    assert unclassified(calls, CLASSES_ON_THE_PAGE, EXPRESSIONS) == []
    said = unclassified(calls, dict(CLASSES_ON_THE_PAGE, tab="text"), EXPRESSIONS)
    assert len(said) == 1 and "classed 'text'" in said[0]
    assert field_classes("| `tab` | text | the words |") == {"tab": "text"}
