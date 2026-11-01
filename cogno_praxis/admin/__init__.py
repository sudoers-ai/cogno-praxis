"""``admin`` — the READ-ONLY vertical of the NEO administrator persona.

NEO talks only to the platform administrator. It analyses the business verticals of this package
and proposes improvements to their skills (prompts, tool texts, tools). This vertical gives it
what it needs to READ them — two read-only tools (``server.py``) over a static reading of the
package (``service.py``) — plus two pure rule modules: the size of a proposed change
(``impact.py``) and the three-layer summary of it (``summary.py``). Requesting, running and merging
a change are not here; wiring the vertical into a host is the host's (``docs/ADMIN.md``).
"""

from cogno_praxis.admin.impact import (
    MAX_SMALL_DIFF_LINES,
    RULES,
    Change,
    Classification,
    PathChange,
    classify,
    escalate,
)
from cogno_praxis.admin.server import build_server
from cogno_praxis.admin.service import (
    AdminError,
    AdminService,
    ToolInfo,
    UnknownVerticalError,
    VerticalInfo,
    discover_verticals,
    read_tool_surface,
)
from cogno_praxis.admin.summary import ChangeReport, Summary, render

__all__ = [
    "build_server",
    "AdminService",
    "AdminError",
    "UnknownVerticalError",
    "ToolInfo",
    "VerticalInfo",
    "discover_verticals",
    "read_tool_surface",
    "MAX_SMALL_DIFF_LINES",
    "RULES",
    "Change",
    "Classification",
    "PathChange",
    "classify",
    "escalate",
    "ChangeReport",
    "Summary",
    "render",
]
