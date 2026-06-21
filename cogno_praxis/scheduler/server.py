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

import json
import os
from datetime import date
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from cogno_praxis.scheduler.engine import SchedulerConfig
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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True))
    def reschedule_appointment(appointment_id: str, new_date: str, new_time: str) -> str:
        """Move an existing appointment to a new date/time in ONE step (keeps the same id).

        Use this for "remarcar" / "mudar o horário" / "trocar para outro dia" — NOT a
        separate cancel + book. Get the appointment_id first (list_appointments) and call
        resolve_date for a relative new date. The new slot must be free and in the future.
        """
        appt = svc.reschedule(appointment_id, new_date, new_time)
        return (f"Rescheduled {appt.appointment_id}: {appt.with_name} with {appt.host_id} "
                f"is now on {appt.date} at {appt.time} [{appt.status}].")

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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_schedule_settings() -> str:
        """Show the tenant's current scheduling rules (hours, lunch, weekends, slot, policy)."""
        s = svc.get_settings()
        return "Schedule settings: " + ", ".join(f"{k}={v}" for k, v in s.items())

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def set_schedule_settings(
        work_start: str = "", work_end: str = "", lunch_start: str = "", lunch_end: str = "",
        slot_duration_minutes: Optional[int] = None,
        work_saturdays: Optional[bool] = None, work_sundays: Optional[bool] = None,
        booking_window_days: Optional[int] = None, cooldown_days: Optional[int] = None,
        max_active_per_client: Optional[int] = None,
    ) -> str:
        """Change the tenant's scheduling rules (only the fields you pass change).

        Times are 'HH:MM'. Use for "abre às 08:00", "passa a atender sábados",
        "máximo 1 agendamento por cliente". Re-computes the available slots immediately.
        """
        overrides = {
            "work_start": work_start or None, "work_end": work_end or None,
            "lunch_start": lunch_start or None, "lunch_end": lunch_end or None,
            "slot_duration_minutes": slot_duration_minutes,
            "work_saturdays": work_saturdays, "work_sundays": work_sundays,
            "booking_window_days": booking_window_days, "cooldown_days": cooldown_days,
            "max_active_per_client": max_active_per_client,
        }
        s = svc.set_settings(**overrides)
        return "Updated schedule settings: " + ", ".join(f"{k}={v}" for k, v in s.items())

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False))
    def set_auto_confirm(host_id: str, auto_confirm: bool) -> str:
        """Set whether a professional's bookings auto-confirm (True) or wait for their
        manual acceptance (False). A professional sets their OWN; a supervisor sets any."""
        host = svc.set_auto_confirm(host_id, auto_confirm)
        return f"{host.host_id} auto_confirm is now {host.auto_confirm}."

    return mcp


def _seeded_service() -> SchedulerService:
    """A small demo service so the standalone server is immediately usable.

    Two bookable professionals (so a SUPERVISOR overseeing *all* agendas is meaningful)
    plus the front desk."""
    store = InMemoryAppointmentStore()
    store.hosts["dr_silva"] = Host("dr_silva", "Dr. Silva", "General Practitioner")
    # dr_souza requires manual acceptance (auto_confirm=False) → bookings stay PENDING until
    # the professional accepts; dr_silva auto-confirms. Demonstrates the per-professional flag.
    store.hosts["dr_souza"] = Host("dr_souza", "Dr. Souza", "Cardiologist", auto_confirm=False)
    store.hosts["ana"] = Host("ana", "Ana Reception", "Front Desk")
    # Optional fixed clock for deterministic harnesses — a host running this server over
    # stdio can set COGNO_SCHEDULER_TODAY so the subprocess agrees with the host's [TODAY]
    # anchor (avoids an off-by-one where "amanhã" resolves against a different "today").
    # Production leaves it unset → the real date.
    iso = os.environ.get("COGNO_SCHEDULER_TODAY")
    clock = (lambda: date.fromisoformat(iso)) if iso else None
    # Optional per-tenant rules + location, injected by the host (same stdio-env channel):
    # COGNO_SCHEDULER_CONFIG = the schedule_config JSON (hours/lunch/weekends/slot);
    # COGNO_SCHEDULER_COUNTRY / _STATE = location → holiday calendar.
    raw = os.environ.get("COGNO_SCHEDULER_CONFIG")
    cfg = SchedulerConfig(json.loads(raw)) if raw else None
    return SchedulerService(store, config=cfg, today=clock,
                            country=os.environ.get("COGNO_SCHEDULER_COUNTRY"),
                            state=os.environ.get("COGNO_SCHEDULER_STATE"))


# In-memory DEMO server for standalone stdio runs / tests (NOT for production —
# a real host injects its own store: see examples/run_with_db.py).
mcp = build_server(_seeded_service())


if __name__ == "__main__":
    mcp.run()
