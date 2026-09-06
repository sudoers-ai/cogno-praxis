"""Every vertical that ships prompts must declare them as package data.

The prompts are plain .txt files next to the code. `setuptools` does NOT pick those up
automatically — each package needs an entry under `[tool.setuptools.package-data]`. Miss one
and nothing fails anywhere near the mistake: the repo has the files, an editable install reads
them off disk, the tests pass, and only an install FROM THE WHEEL comes up with an empty
prompt.

That is exactly what happened to the CLOSER (2026-08-03). `scheduler`, `bookkeeper` and
`coordinator` were declared; `closer` was not. The host's own
`test_every_catalog_persona_actually_loads_all_four_prompt_slots` caught it — but only in CI,
where the libs install from pinned wheels, and that pipeline had been red on unrelated ruff/
mypy drift for long enough that the real failure underneath was never read. The demo box runs
from source, so it never showed there either.

The Docker image builds from the same pinned wheels, so this shipped a persona whose system
prompt was the empty string.

This test derives the expectation from the FILESYSTEM rather than restating the list, so a new
vertical is covered the day it is added instead of the day someone remembers.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PKG = ROOT / "cogno_praxis"

# Parsed with a regex rather than tomllib: the supported floor is 3.10, where tomllib does not
# exist, and pulling `tomli` in as a dev dependency to read one line of our own config is a
# worse trade than a targeted pattern.
_ENTRY = re.compile(r'^"cogno_praxis\.(?P<name>[a-z_]+)"\s*=\s*\[(?P<globs>[^\]]*)\]', re.M)


def _declared() -> set[str]:
    text = (ROOT / "pyproject.toml").read_text()
    section = text.split("[tool.setuptools.package-data]", 1)
    assert len(section) == 2, "package-data section vanished — this test guards it"
    body = section[1].split("\n[", 1)[0]
    return {m.group("name") for m in _ENTRY.finditer(body) if "prompts/" in m.group("globs")}


def _on_disk() -> set[str]:
    return {p.parent.name for p in PKG.glob("*/prompts") if any(p.glob("*.txt"))}


def test_every_vertical_with_prompts_declares_them_as_package_data():
    on_disk, declared = _on_disk(), _declared()
    missing = on_disk - declared
    assert not missing, (
        f"{sorted(missing)} ship prompt files that would NOT be installed from a wheel — add "
        f'\'"cogno_praxis.<name>" = ["prompts/*.txt"]\' to [tool.setuptools.package-data]. '
        f"An editable install hides this; the wheel the image builds from does not."
    )


def test_no_stale_package_data_entry():
    """The mirror: an entry for a vertical that no longer ships prompts is dead config, and dead
    config is what makes the live entries easy to stop reading."""
    stale = _declared() - _on_disk()
    assert not stale, f"{sorted(stale)} declare prompts/*.txt but ship none"


#: Modules that shadow a stdlib name and are STILL HERE, each with the reason it has not bitten.
#: A list that may only shrink — ``test_the_shadow_exemption_has_no_stale_entries`` fails on an
#: entry that no longer collides, and the sweep below fails on a name that is not in here.
_SHADOWS_ALLOWED: "dict[str, str]" = {
    # Shipped with the vertical, and latent rather than harmless. ``types`` is imported during
    # interpreter STARTUP (``site`` pulls it in), so ``sys.modules['types']`` already holds the
    # standard library one before any sibling directory reaches the head of ``sys.path`` — the
    # shadow never gets asked. That is protection by ORDERING, not by design: it holds only for
    # names Python loads before us, which is exactly the line ``calendar`` fell on the wrong
    # side of. Renaming it is a separate change; it is written down here so the next author
    # inherits the reason instead of the silence.
    "coordinator/types.py": "already in sys.modules before any sibling dir joins sys.path",
}


def test_no_module_shadows_a_standard_library_name():
    """A module named after a stdlib one is a landmine in exactly this package layout.

    Every vertical ships a FastMCP server that the host spawns **as a script**
    (``python -m cogno_praxis.<vertical>.server``, and the integration suite runs the file path
    directly). Running a file puts its OWN DIRECTORY at the head of ``sys.path``, so a module
    beside it wins over the standard library for the whole process — for our code and for
    everybody else's.

    Measured, not imagined: the calendar export shipped for twenty minutes as
    ``coordinator/calendar.py``, and the integration suite came up with
    ``ImportError: cannot import name 'timegm' from 'calendar'`` — raised inside ``httpx``,
    three libraries away, because ``http.cookiejar`` asked the standard library for a function
    and got ours. ``coordinator/service.py`` imports ``calendar`` too, so the same collision was
    live INSIDE this package. The file is ``ics.py`` now.

    Derived from ``sys.stdlib_module_names`` rather than a hand list, so it covers the name
    nobody thought of.
    """
    unexplained = sorted(set(_collisions()) - set(_SHADOWS_ALLOWED))
    assert not unexplained, (
        f"these shadow a standard-library module for any process that runs a sibling file as a "
        f"script: {unexplained}. Rename them — the failure surfaces far from the cause, inside "
        f"whichever third-party library asks the stdlib for that name first. If one of them is "
        f"genuinely safe, say WHY in _SHADOWS_ALLOWED; silence is how the last one shipped.")


def test_the_shadow_exemption_has_no_stale_entries():
    """An exemption naming a file that no longer collides makes the sweep read as narrower than
    it is — and is how such a list stops being read at all."""
    stale = sorted(set(_SHADOWS_ALLOWED) - set(_collisions()))
    assert not stale, f"_SHADOWS_ALLOWED names files that no longer shadow anything: {stale}"


def _collisions() -> "list[str]":
    import sys
    return sorted(f"{path.parent.name}/{path.name}"
                  for path in PKG.rglob("*.py")
                  if path.stem in sys.stdlib_module_names and path.stem != "__init__")
