"""The ``scheduler`` (agenda) vertical as a FastMCP server.

A thin MCP wrapper over :class:`SchedulerService`. The host connects to this server
via ``cogno-mcp`` (``MCPDispatcher``), so the EGO sees these as ordinary tools. Tool
``annotations`` (readOnlyHint / destructiveHint) flow through cogno-mcp into the
EGO's read-only mask + confirmation gate — e.g. ``cancel_appointment`` is destructive
and the EGO will hold it for confirmation.

``build_server(service)`` is the **only injection seam**: the host builds a service
over its own ``AppointmentStore`` adapter and runs it (see ``examples/run_with_db.py``).
The module-level ``mcp`` below is an **in-memory demo** for standalone runs and tests.

Run the demo standalone (stdio):  ``python -m cogno_praxis.scheduler.server``
"""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cogno_praxis.scheduler.service import SchedulerService
from cogno_praxis.scheduler.store import Host, InMemoryAppointmentStore


def build_server(service: Optional[SchedulerService] = None, *, name: str = "cogno-scheduler") -> FastMCP:
    """Build a FastMCP server bound to a service (inject a store-backed one in prod/tests)."""
    svc = service or SchedulerService()
    mcp = FastMCP(name)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_schedulable_hosts() -> str:
        """List the people/resources that can be booked."""
        hosts = svc.list_hosts()
        if not hosts:
            return "No schedulable hosts are configured."
        return "\n".join(f"{h.host_id}: {h.name}" + (f" ({h.role})" if h.role else "")
                         for h in hosts)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def resolve_date(expression: str) -> str:
        """Resolve a relative/named date ('amanhã', 'próxima sexta', 'quarta') to YYYY-MM-DD.

        Always call this for a relative or weekday phrase instead of computing the date
        yourself, then use the returned YYYY-MM-DD in check_availability / book_appointment.
        """
        iso = svc.resolve_date(expression)
        return f"{expression} = {iso}"

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def check_availability(host_id: str, date: str) -> str:
        """List free time slots for a host on a date (YYYY-MM-DD, from tomorrow on)."""
        free = svc.check_availability(host_id, date)
        if not free:
            return f"{host_id} has no free slots on {date}."
        return f"Free slots for {host_id} on {date}: " + ", ".join(free)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def book_appointment(host_id: str, date: str, time: str, with_name: str,
                         notes: str = "") -> str:
        """Book an appointment with a host at a date/time for a client (status PENDING)."""
        appt = svc.book(host_id, date, time, with_name, notes)
        return (f"Booked {appt.appointment_id}: {with_name} with {host_id} "
                f"on {date} at {time} [{appt.status}].")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def block_schedule(host_id: str, date: str, start_time: str = "", end_time: str = "",
                       description: str = "") -> str:
        """Make a host unavailable, removing slots from availability (a self-occupation).

        No start_time blocks the WHOLE working day; start_time alone blocks one slot; both
        block every slot in [start_time, end_time). Refuses if a client booking sits in the
        range. Use for "Dr. Silva is out on Friday" / "block the afternoon".
        """
        blocks = svc.block_schedule(host_id, date, start_time=start_time,
                                    end_time=end_time, description=description)
        if not blocks:
            return f"{host_id} had no free slots to block on {date} (already taken/blocked)."
        return (f"Blocked {host_id} on {date} at: "
                f"{', '.join(b.time for b in blocks)} [{blocks[0].notes}].")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_appointments(with_name: str = "", host_id: str = "") -> str:
        """List appointments, optionally filtered by client name or host."""
        appts = svc.list_appointments(host_id=host_id or None, with_name=with_name or None)
        if not appts:
            return "No appointments found."
        return "\n".join(f"{a.appointment_id}: {a.with_name} with {a.host_id} "
                         f"on {a.date} at {a.time} [{a.status}]" for a in appts)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def update_appointment_status(appointment_id: str, new_status: str) -> str:
        """Move an appointment along its lifecycle (CONFIRMED / COMPLETED / etc.)."""
        appt = svc.update_status(appointment_id, new_status)
        return f"Appointment {appt.appointment_id} is now {appt.status}."

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
    def cancel_appointment(appointment_id: str, reason: str = "") -> str:
        """Cancel an existing appointment by id (optionally with a reason)."""
        appt = svc.cancel(appointment_id, reason)
        suffix = f" — {appt.cancel_reason}" if appt.cancel_reason else ""
        return (f"Cancelled {appt.appointment_id} ({appt.with_name} on {appt.date} "
                f"at {appt.time}){suffix}.")

    return mcp


def _seeded_service() -> SchedulerService:
    """A small demo service so the standalone server is immediately usable."""
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "General Practitioner")
    store.hosts["ana"] = Host("ana", "Ana Reception", "Front Desk")
    return SchedulerService(store)


# In-memory DEMO server for standalone stdio runs / tests (NOT for production —
# a real host injects its own store: see examples/run_with_db.py).
mcp = build_server(_seeded_service())


if __name__ == "__main__":
    mcp.run()
