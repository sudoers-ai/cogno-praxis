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
