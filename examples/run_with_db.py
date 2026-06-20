"""Production entrypoint pattern: run the scheduler over YOUR database.

The vertical's only injection seam is ``build_server(service)``. In production the
*host* writes a tiny entrypoint like this one: it builds a ``SchedulerService`` over a
real ``AppointmentStore`` adapter (Postgres/Redis/your DB) and runs the FastMCP server.

The DB connection is born **here, inside the vertical's own process** — it never crosses
the MCP boundary, and the host that connects over stdio/HTTP need not share the pool.
Multi-tenancy is just *which* store/DSN you build here (one process per tenant, or a
tenant-scoped DSN); the scheduler itself stays tenant-agnostic.

The module-level demo server (``cogno_praxis.scheduler.server:mcp``) is in-memory and is
NOT for production — this file is what you point your stdio/HTTP runner at instead.

    python examples/run_with_db.py        # serves over stdio, backed by the adapter below
"""

from __future__ import annotations

from typing import Optional

from cogno_praxis.scheduler.server import build_server
from cogno_praxis.scheduler.service import SchedulerService
from cogno_praxis.scheduler.store import Appointment, Host


class MyAppointmentStore:
    """Sketch of a host-owned adapter implementing the AppointmentStore port.

    Replace the bodies with real DB calls (the connection/pool lives on this object,
    created from an env DSN). Shown here in-memory just so the example runs.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn                       # e.g. os.environ["SCHEDULER_DSN"]
        # self._pool = create_pool(dsn)       # ← your real connection lives here
        self._hosts: dict[str, Host] = {"dr_silva": Host("dr_silva", "Dr. Silva", "GP")}
        self._appts: dict[str, Appointment] = {}

    def list_hosts(self) -> list[Host]:
        return list(self._hosts.values())

    def get_host(self, host_id: str) -> Optional[Host]:
        return self._hosts.get(host_id)

    def booked_times(self, host_id: str, date: str) -> set[str]:
        from cogno_praxis.scheduler.store import ACTIVE_STATUS
        return {a.time for a in self._appts.values()
                if a.host_id == host_id and a.date == date and a.status in ACTIVE_STATUS}

    def add(self, appointment: Appointment) -> None:
        self._appts[appointment.appointment_id] = appointment

    def get(self, appointment_id: str) -> Optional[Appointment]:
        return self._appts.get(appointment_id)

    def list(self, *, host_id: Optional[str] = None,
             with_name: Optional[str] = None) -> list[Appointment]:
        out = list(self._appts.values())
        if host_id is not None:
            out = [a for a in out if a.host_id == host_id]
        if with_name is not None:
            out = [a for a in out if a.with_name.lower() == with_name.lower()]
        return out

    def update(self, appointment: Appointment) -> None:
        self._appts[appointment.appointment_id] = appointment


def build() -> object:
    store = MyAppointmentStore(dsn="postgresql://localhost/cogno")   # ← from env in real life
    return build_server(SchedulerService(store))


if __name__ == "__main__":
    build().run()   # type: ignore[attr-defined]   # FastMCP.run() over stdio
