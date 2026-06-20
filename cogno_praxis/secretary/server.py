"""SECRETARY (reception) vertical as a FastMCP server.

A thin MCP wrapper over :class:`SecretaryService`. The host connects to this server
via ``cogno-mcp`` (``MCPDispatcher``), so the EGO sees these as ordinary tools. Tool
``annotations`` (readOnlyHint / destructiveHint) flow through cogno-mcp into the
EGO's read-only mask + confirmation gate — e.g. ``cancel_appointment`` is destructive
and the EGO will hold it for confirmation.

Run standalone (stdio):  ``python -m cogno_praxis.secretary.server``
"""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cogno_praxis.secretary.service import SecretaryService
from cogno_praxis.secretary.store import Host, InMemoryAppointmentStore


def build_server(service: Optional[SecretaryService] = None, *, name: str = "cogno-secretary") -> FastMCP:
    """Build a FastMCP server bound to a service (inject a seeded one in tests)."""
    svc = service or SecretaryService()
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
    def check_availability(host_id: str, date: str) -> str:
        """List free time slots for a host on a date (YYYY-MM-DD)."""
        free = svc.check_availability(host_id, date)
        if not free:
            return f"{host_id} has no free slots on {date}."
        return f"Free slots for {host_id} on {date}: " + ", ".join(free)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def book_appointment(host_id: str, date: str, time: str, with_name: str,
                         notes: str = "") -> str:
        """Book an appointment with a host at a date/time for a client."""
        appt = svc.book(host_id, date, time, with_name, notes)
        return (f"Booked {appt.appointment_id}: {with_name} with {host_id} "
                f"on {date} at {time}.")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_appointments(with_name: str = "", host_id: str = "") -> str:
        """List appointments, optionally filtered by client name or host."""
        appts = svc.list_appointments(host_id=host_id or None, with_name=with_name or None)
        if not appts:
            return "No appointments found."
        return "\n".join(f"{a.appointment_id}: {a.with_name} with {a.host_id} "
                         f"on {a.date} at {a.time} [{a.status}]" for a in appts)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
    def cancel_appointment(appointment_id: str) -> str:
        """Cancel an existing appointment by id."""
        appt = svc.cancel(appointment_id)
        return f"Cancelled {appt.appointment_id} ({appt.with_name} on {appt.date} at {appt.time})."

    return mcp


def _seeded_service() -> SecretaryService:
    """A small demo service so the standalone server is immediately usable."""
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "General Practitioner")
    store.hosts["ana"] = Host("ana", "Ana Reception", "Front Desk")
    return SecretaryService(store)


# Module-level server for standalone stdio runs (seeded with demo hosts).
mcp = build_server(_seeded_service())


if __name__ == "__main__":
    mcp.run()
