"""The contact's name by reference — the pairs, the swap, and the files it must never touch.

**Why.** A host keeps the contact's label inside a fence of data and has the prompt point at
it; the only path left in line is the ``{identity_label}`` the persona templates interpolate
(21 places, 11 files, 5 verticals — derived below). A label that is itself an order with no
sentence terminator is not cut by any form a name takes, and one of these sentences tells the
voice to greet by that string.

``cogno_praxis.contact_wording`` holds the two wordings of each sentence side by side and a
function that swaps them. What is pinned here:

* **OFF is the shipped file.** The 11 templates are byte for byte the ones of ``origin/main``
  ``423a755`` (their ``sha256``, below): this change does not edit a template, and nothing
  swaps a sentence unless a caller asks. CONTROL, green before and after.
* **Sync, both ways.** Every ``today`` is in its file exactly once and names the contact
  exactly once; every file that names the contact has an entry and every entry a file; after
  the swap no ``{identity_label}`` is left — so a NEW sentence with the placeholder and no pair
  fails here.
* **The table of the occurrences is DERIVED** (:data:`IN_LINE`): the files are read and
  counted, and a template that gains or loses one moves it.
* **The three rules of the wording**: one pointer per slot; a spoken example carries the
  marker and never the pointer; the judge's sentence still licenses the user's own name.
* **The language is the template's**: «the contact» in the English prompts, «o contato» in
  the Portuguese ones, never one inside the other.

The model half — what a model DOES with these sentences (does the voice still greet by the
right name; does it ever say the marker) — is not here and cannot be: it is measured
downstream, with a model, in both wordings.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

PKG = Path(__import__("cogno_praxis").__file__).resolve().parent
LABEL = "{identity_label}"
REF = "{contact_reference}"

#: ``sha256`` of each template that names the contact, at ``origin/main`` ``423a755``. This
#: change must not move one of them. A later, deliberate edit of a template regenerates its
#: line here AND its pair in ``contact_wording.WORDINGS`` — the sync tests say which.
AT_MAIN = {
    ("bookkeeper", "system"): "8d6535d3326748e703e56a15bdc5ff5c546ae0fb47dc2ba38f876b61c3e45665",
    ("bookkeeper", "voice"): "1b65181573edc71b964a686d96c92ab94b664bb094b88d4911e034536c95d347",
    ("closer", "system"): "c5b30b8faf18562ec7936965e16fe59a8570d4bc9d67654c3156f9c170cf623d",
    ("closer", "voice"): "ecf7b265950d2b9797fb2329c430fad558988c07e0e4652228ec81e0a7bb73c1",
    ("coordinator", "system"): "5085d29f398179ea208eb2b81f28b2a51489004b12e6c7f2f3527f02dcee1e89",
    ("coordinator", "voice"): "21ca2bcf50fc42613687c6cb61f40ec6c0510b6384061a7c22bf8d45308b9ead",
    ("interviewer", "system"): "640c76109c62a142f6304af1b8592b79e1c9808735a3daf067c24f3abc42be27",
    ("interviewer", "voice"): "0dfe458c1778ed53dfcb8cadbcfdc69993ecd8cc7233e7ca3dcc5de9a8b1887e",
    ("scheduler", "limits"): "92becaf1d23c56570833082fe1507e01c0afe3a52922ee8404ed671a53a6a2a4",
    ("scheduler", "system"): "49d2c8ce3706642f1baeef66ea2717be061f2262ccd6fa83f132e08cd93d58b2",
    ("scheduler", "voice"): "68c17d7ea87916af677d8d03f532975de41c729b90e9e4b3587a5ddc5e68ae9b",
}

#: How many times each template names the contact in line — 21 in 11 files. DERIVED: the test
#: counts the files. The by-reference count is zero for every one of them.
IN_LINE = {
    ("scheduler", "system"): 2, ("scheduler", "limits"): 1, ("scheduler", "voice"): 5,
    ("coordinator", "system"): 5, ("coordinator", "voice"): 2,
    ("bookkeeper", "system"): 1, ("bookkeeper", "voice"): 1,
    ("closer", "system"): 1, ("closer", "voice"): 1,
    ("interviewer", "system"): 1, ("interviewer", "voice"): 1,
}

PORTUGUESE = {"closer", "interviewer"}
KEYS = sorted(AT_MAIN)


def _cw():
    """Imported inside each test: the digest control must stay green on a tree without it."""
    from cogno_praxis import contact_wording
    return contact_wording


def _path(vertical: str, slot: str) -> Path:
    return PKG / vertical / "prompts" / f"{slot}.txt"


def _text(vertical: str, slot: str) -> str:
    return _path(vertical, slot).read_text(encoding="utf-8")


def _swapped(vertical: str, slot: str) -> str:
    return _cw().by_reference(vertical, slot, _text(vertical, slot))


def _render(text: str, context: "dict[str, str]") -> str:
    """How a host fills the single-brace placeholders: known ones replaced, the rest left."""
    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}",
                  lambda m: context.get(m.group(1), m.group(0)), text)


def _quoted(text: str) -> "list[str]":
    """The double-quoted spans of a template, paired in order (every file has an even count)."""
    assert text.count('"') % 2 == 0
    return re.findall(r'"([^"]*)"', text)


# ── 1. OFF: the files are the ones of main ───────────────────────────────────────────────

@pytest.mark.parametrize("key", KEYS, ids=lambda k: "/".join(k))
def test_control_the_template_is_byte_for_byte_the_one_of_main(key):
    assert hashlib.sha256(_path(*key).read_bytes()).hexdigest() == AT_MAIN[key]


def test_control_the_templates_that_name_the_contact_are_these_eleven():
    """…and the count per file is the declared table: 21 occurrences."""
    found = {(p.parent.parent.name, p.stem): p.read_text(encoding="utf-8").count(LABEL)
             for p in PKG.glob("*/prompts/*.txt")}
    naming = {k: n for k, n in found.items() if n}
    assert naming == IN_LINE
    assert sum(naming.values()) == 21 and len(naming) == 11
    assert len({v for v, _ in naming}) == 5
    assert not any(slot == "scope" for _, slot in naming)       # a scope names nobody


def test_nothing_is_swapped_unless_asked():
    """The module has a function, not a switch: importing it changes no template."""
    _cw()
    for key in KEYS:
        assert hashlib.sha256(_path(*key).read_bytes()).hexdigest() == AT_MAIN[key]


# ── 2. sync, both ways ───────────────────────────────────────────────────────────────────

def test_the_table_and_the_files_cover_each_other():
    assert sorted(_cw().WORDINGS) == KEYS == sorted(IN_LINE)


@pytest.mark.parametrize("key", KEYS, ids=lambda k: "/".join(k))
def test_every_today_is_in_its_file_exactly_once_and_names_the_contact_once(key):
    text = _text(*key)
    pairs = _cw().WORDINGS[key]
    assert len(pairs) == IN_LINE[key]                      # one pair per occurrence
    for today, wording in pairs:
        assert text.count(today) == 1, today
        assert today.count(LABEL) == 1, today
        assert LABEL not in wording, wording
    assert len({today for today, _ in pairs}) == len(pairs)


@pytest.mark.parametrize("key", KEYS, ids=lambda k: "/".join(k))
def test_by_reference_no_template_names_the_contact_in_line(key):
    """The count the table declares goes to ZERO — and a sentence with the placeholder that no
    pair covers would be left here."""
    assert _text(*key).count(LABEL) == IN_LINE[key]        # control: it is there before
    assert _swapped(*key).count(LABEL) == 0


@pytest.mark.parametrize("key", KEYS, ids=lambda k: "/".join(k))
def test_by_reference_changes_the_paired_sentences_and_nothing_else(key):
    """Take each ``by_reference`` back out and the text is main's again, byte for byte."""
    text = _swapped(*key)
    assert text != _text(*key)
    for today, wording in _cw().WORDINGS[key]:
        assert text.count(wording) == 1, wording
        text = text.replace(wording, today)
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == AT_MAIN[key]


def test_a_new_sentence_with_no_pair_is_seen():
    """The mutation, written as a twin: a template that gains a mention keeps it after the
    swap, which is exactly what the zero above forbids."""
    grown = _text("bookkeeper", "voice") + "\nThank {identity_label} at the end.\n"
    assert _cw().by_reference("bookkeeper", "voice", grown).count(LABEL) == 1


# ── 3. the swap itself ───────────────────────────────────────────────────────────────────

def test_a_template_with_no_entry_comes_back_the_same_object():
    cw = _cw()
    for p in sorted(PKG.glob("*/prompts/scope.txt")):
        text = p.read_text(encoding="utf-8")
        assert cw.by_reference(p.parent.parent.name, "scope", text) is text
    text = _text("scheduler", "voice")
    assert cw.by_reference("a_vertical_nobody_ships", "voice", text) is text
    assert cw.by_reference("scheduler", "a_slot_nobody_ships", text) is text


def test_a_text_none_of_the_sentences_are_in_comes_back_the_same_object():
    cw = _cw()
    for text in ("", "Nothing here names anybody.", "{identity_label}"):
        assert cw.by_reference("scheduler", "voice", text) is text


def test_the_swap_is_keyed_by_vertical_and_slot():
    """The same sentence has two wordings in two verticals (the bookkeeper's opening points
    at the name; the coordinator's does not, its pointer is further down), so the key matters."""
    cw = _cw()
    line = "You are X, acting for {identity_label}."
    assert cw.by_reference("coordinator", "system", line) == "You are X, acting for the contact."
    assert REF in cw.by_reference("bookkeeper", "system", line)
    assert cw.by_reference("coordinator", "voice", line) is line


def test_applying_it_twice_is_applying_it_once():
    for key in KEYS:
        once = _swapped(*key)
        assert _cw().by_reference(*key, once) is once


def test_the_swap_survives_a_host_that_filled_its_blocks_first():
    """A host fills ``{{ROLE_CAPABILITIES}}`` around these sentences before or after the swap:
    the result is the same text either way."""
    cw = _cw()
    raw = _text("scheduler", "system")
    assert "{{ROLE_CAPABILITIES}}" in raw
    block = "- book an appointment\n- list the day"
    assert (cw.by_reference("scheduler", "system", raw.replace("{{ROLE_CAPABILITIES}}", block))
            == cw.by_reference("scheduler", "system", raw).replace("{{ROLE_CAPABILITIES}}", block))


# ── 4. the three rules of the wording ────────────────────────────────────────────────────

@pytest.mark.parametrize("key", KEYS, ids=lambda k: "/".join(k))
def test_there_is_exactly_one_pointer_per_slot(key):
    assert _swapped(*key).count(REF) == 1
    assert _text(*key).count(REF) == 0                     # control: main has none


def test_the_marker_is_the_portuguese_literal():
    """Pinned as a LITERAL, on purpose. The marker sits inside the spoken examples, which are
    Portuguese (pt-BR, «contato»), and it is what a CONTACT reads if a model ever copies an
    example without filling it: «Bom dia, <nome do contato>!» is a visible slip in the reader's
    own language, «<contact name>» is a foreign string in the middle of a Portuguese greeting.
    It is also the string a host counts in a reply, so changing it silently un-counts the leak."""
    assert _cw().NAME_MARKER == "<nome do contato>"
    # …and it is the same language as the examples it sits in
    examples = [q for key in KEYS for q in _quoted(_swapped(*key)) if _cw().NAME_MARKER in q]
    assert len(examples) == 4
    assert all(re.search(r"\b(Bom dia|você|Prontinho|aulas)\b", q) for q in examples)


def test_the_placeholder_names_are_the_exported_constants():
    cw = _cw()
    assert LABEL == "{" + cw.CONTACT_LABEL + "}" and REF == "{" + cw.CONTACT_REFERENCE + "}"
    assert cw.NAME_MARKER.startswith("<") and cw.NAME_MARKER.endswith(">")
    assert "{" not in cw.NAME_MARKER                       # a marker is never a placeholder


@pytest.mark.parametrize("key", KEYS, ids=lambda k: "/".join(k))
def test_a_spoken_example_carries_the_marker_and_never_the_pointer(key):
    cw = _cw()
    spoken = [q for q in _quoted(_text(*key)) if LABEL in q]
    after = _quoted(_swapped(*key))
    assert not any(REF in q for q in after)                # nothing in quotes points
    assert sum(cw.NAME_MARKER in q for q in after) == len(spoken)
    for today, wording in cw.WORDINGS[key]:
        # the name sits inside an OPEN quote of the sentence → it is a spoken example
        if today[:today.index(LABEL)].count('"') % 2:
            assert cw.NAME_MARKER in wording and REF not in wording, wording
        else:
            assert cw.NAME_MARKER not in wording, wording


def test_the_examples_are_where_they_were_measured():
    """Control for the test above — it would pass over a table with no example at all."""
    spoken = {key: sum(LABEL in q for q in _quoted(_text(*key))) for key in KEYS}
    assert {k: n for k, n in spoken.items() if n} == {("scheduler", "voice"): 3,
                                                      ("coordinator", "system"): 1}


def test_wherever_the_marker_is_used_a_sentence_says_what_it_stands_for():
    cw = _cw()
    for key in KEYS:
        text = _swapped(*key)
        if cw.NAME_MARKER in text:
            assert f"{cw.NAME_MARKER} stands for the contact's name" in text, key
            assert "never the marker" in text, key


def test_the_instruction_to_greet_by_name_points_at_the_name_and_calls_it_data():
    """The legitimate use is kept: the voice is still told to greet by name, and told where
    the name is."""
    voice = _swapped("scheduler", "voice")
    assert "- Greet the contact by name" in voice
    line = next(ln for ln in voice.splitlines() if ln.startswith("- Greet the contact by name"))
    assert REF in line and "which is data" in line and "never the label" in line
    assert "and use it naturally." in line                 # the rest of the sentence is main's
    assert "- Greet {identity_label} by name and use it naturally." in _text("scheduler", "voice")


def test_the_judge_is_still_told_the_user_s_own_name_is_legitimate():
    limits = _swapped("scheduler", "limits")
    para = limits[limits.index("KNOWN USER (not fabrication)"):]
    para = para[:para.index("\n\n")] if "\n\n" in para else para
    assert REF in para
    for kept in ("Using this user's own name", "is CORRECT and expected",
                 "never flag the user's own name", "as invented or unsupported"):
        assert kept in para, kept
    assert "the assistant is legitimately speaking with\nthe contact (" in para


# ── 5. the language is the template's ────────────────────────────────────────────────────

@pytest.mark.parametrize("key", KEYS, ids=lambda k: "/".join(k))
def test_each_wording_is_in_the_language_of_its_template(key):
    vertical, _ = key
    cw = _cw()
    for today, wording in cw.WORDINGS[key]:
        wording = wording.replace(cw.NAME_MARKER, "")       # the marker is Portuguese by design:
        added = wording                                     # it sits inside a Portuguese example
        for kept in re.split(re.escape(LABEL), today):      # what the pair ADDS to main's words
            added = added.replace(kept, " ") if kept.strip() else added
        if vertical in PORTUGUESE:
            assert "contato" in wording and "the contact" not in wording, wording
            assert not re.search(r"\b(their|name|written|under|say|never)\b", added), wording
        else:
            assert "o contato" not in wording, wording
            assert not re.search(r"\b(escrito|dado|diga|nunca|rótulo)\b", added), wording


def test_control_the_two_languages_are_the_ones_the_files_are_in():
    for vertical in sorted({v for v, _ in KEYS}):
        opening = _text(vertical, "system").splitlines()[0]
        assert opening.startswith("Você é" if vertical in PORTUGUESE else "You are"), vertical


# ── 6. rendered: the name a host fills in ────────────────────────────────────────────────

NAME = "Marta Zelbrith"
POINTER = "«[NOME]»"                                       # a host's reference, invented here


@pytest.mark.parametrize("key", KEYS, ids=lambda k: "/".join(k))
def test_rendered_the_name_is_in_line_today_and_gone_by_reference(key):
    context = {"identity_label": NAME, "contact_reference": POINTER,
               "tenant_name": "Escola Exemplo", "secretary_name": "Lia",
               "identity_role": "EMPLOYEE", "identity_email": "marta@example.com"}
    today = _render(_text(*key), context)
    assert today.count(NAME) == IN_LINE[key]               # control: the declared table
    assert POINTER not in today
    swapped = _render(_swapped(*key), context)
    assert NAME not in swapped
    assert swapped.count(POINTER) == 1
    assert LABEL not in swapped and REF not in swapped     # nothing left to fill


def test_rendered_a_host_that_does_not_fill_the_pointer_leaves_it_visible():
    """An unfilled pointer stays as the literal placeholder — loud, never an empty hole."""
    context = {"identity_label": NAME}
    assert REF in _render(_swapped("closer", "voice"), context)
