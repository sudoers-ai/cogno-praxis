"""The ``NO SUCH DISCIPLINE`` line — written here, and READ back here, in one definition.

``get_professor_schedule`` drops a ``discipline`` that names nothing in the caller's schedule
(M6-c) and says so in one line that also lists the disciplines the read DOES hold. It was a
FOOTER, under the whole listing; it now OPENS the listing (``server._fmt_list``), because the
miss is the answer to what was asked and a reply built from the top of the text left it out
(the module keeps its name: the other lines of the read report are still footers). Two
readers use that line:

* the EXECUTOR and the judge read it as prose, and that is why it is prose;
* the host reads it as a CLOSED LIST: «Não encontrei X. Você quis dizer: A / B?» (VQD-2(a),
  ``cogno-host``'s ``did_you_mean_discipline``) may only name disciplines this list holds,
  copied byte for byte.

**Every name is a JSON string literal, and that is the whole point of this module.** The list was
joined with ``", "``, so a discipline whose own name carries a comma («Ética, Política e
Sociedade») read back as THREE names, two of which are on no sheet — and an option the host
offered from such a split would be a discipline the contact cannot be shown classes of. A JSON
literal round-trips any name, quotes and backslashes included, and reads to a person (and a model)
exactly like the quoted ``"X"`` this line already opened with. For a plain name the bytes of the
asked value are unchanged (``json.dumps("Bancos NoSQL") == '"Bancos NoSQL"'``).

:func:`parse_unmatched_discipline` is the ONLY reader. A consumer that parses this line with its
own regex is a second copy of a contract that just changed once; ``tests/unit/test_footers.py``
pins the round trip over the names that broke the old one.
"""

from __future__ import annotations

import json
import re
from typing import Optional, Sequence

__all__ = ["NO_SUCH_DISCIPLINE", "SAY_THE_MISS_FIRST", "unmatched_discipline_line",
           "parse_unmatched_discipline"]

#: The marker that opens the line. Matched literally by :func:`parse_unmatched_discipline`.
NO_SUCH_DISCIPLINE = "NO SUCH DISCIPLINE"

#: What the list says when the read holds no discipline at all.
NONE_IN_SCHEDULE = "(none in this schedule)"

_JSON_STR = r'"(?:[^"\\]|\\.)*"'
_LINE = re.compile(
    rf"{NO_SUCH_DISCIPLINE}: (?P<asked>{_JSON_STR}) does not match any discipline .*?"
    rf"The disciplines here are: (?P<known>{_JSON_STR}(?:, {_JSON_STR})*|"
    rf"{re.escape(NONE_IN_SCHEDULE)})\. If the user meant one of them")


def _lit(text: str) -> str:
    return json.dumps(str(text), ensure_ascii=False)


#: What the line asks of the reply, between the miss and the reason for the unfiltered list.
#: A constant so a test can name it; the wording is the measured defect's (the voice listed the
#: classes and never said the name matched nothing).
SAY_THE_MISS_FIRST = (
    "Tell the user exactly that, plainly, as the reply's FIRST sentence and before any class "
    "— a reply that only lists the classes leaves them not knowing that the name they asked "
    "for matched nothing.")


def unmatched_discipline_line(asked: str, known: Sequence[str]) -> str:
    """The line for a ``discipline`` that matched nothing. ``known`` in the order given.

    It OPENS the listing (``server._fmt_list`` writes it above the classes, never under them),
    and it is worded to sit there: the miss first, as a sentence that reads as the answer, then
    why the classes below it are unfiltered. Measured on a real read of this shape: with this
    line as the LAST paragraph, after the whole listing, the reply listed the classes and left
    the negative out 3 times in 5. Nothing in the wording points "above" or "below", so the
    line stays true wherever a caller puts it."""
    names = ", ".join(_lit(k) for k in known) or NONE_IN_SCHEDULE
    return (f"{NO_SUCH_DISCIPLINE}: {_lit(asked)} does not match any discipline "
            f"in this schedule. {SAY_THE_MISS_FIRST} It may be the name of a programme or "
            f"course, not of a discipline, so the classes listed here are the upcoming classes "
            f"WITHOUT that filter. The disciplines here are: {names}. If the user meant one of "
            f"them, call again with `discipline` set to it.")


def parse_unmatched_discipline(text: object) -> "Optional[tuple[str, tuple[str, ...]]]":
    """``(asked, known)`` from a tool result that carries the footer, or ``None``.

    ``known`` is exactly the list the tool wrote, in its order (``()`` for a read with no
    discipline). Pure; never raises — anything that is not this line is ``None``."""
    if not isinstance(text, str) or NO_SUCH_DISCIPLINE not in text:
        return None
    m = _LINE.search(text)
    if m is None:
        return None
    try:
        asked = json.loads(m.group("asked"))
        raw = m.group("known")
        known = () if raw == NONE_IN_SCHEDULE else tuple(json.loads(f"[{raw}]"))
    except ValueError:
        return None
    if not isinstance(asked, str) or not all(isinstance(k, str) for k in known):
        return None
    return asked, known
