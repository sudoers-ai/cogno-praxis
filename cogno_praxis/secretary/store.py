"""Domain types + the persistence port for the SECRETARY (reception) vertical.

Appointments are **structured domain data**, not conversation memory — so the
vertical owns its own store port (the homeo pattern: a Protocol + an in-memory
default; the host plugs a real DB adapter). This keeps even the product vertical
infra-agnostic. cogno-engram stays for episodic/KG memory, not appointment rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass
class Host:
    """Someone who can be booked (a professional, a room, a resource)."""

    host_id: str
    name: str
    role: str = ""


@dataclass
class Appointment:
    appointment_id: str
    host_id: str
    date: str            # ISO date "YYYY-MM-DD"
    time: str            # "HH:MM"
    with_name: str       # who the appointment is with (the client)
    status: str = "booked"   # booked | cancelled | completed
    notes: str = ""


@runtime_checkable
class AppointmentStore(Protocol):
    """Persistence port. The host injects a real adapter; the default is in-memory."""

    def list_hosts(self) -> list[Host]: ...
    def get_host(self, host_id: str) -> Optional[Host]: ...
    def booked_times(self, host_id: str, date: str) -> set[str]: ...
    def add(self, appointment: Appointment) -> None: ...
    def get(self, appointment_id: str) -> Optional[Appointment]: ...
    def list(self, *, host_id: Optional[str] = None,
             with_name: Optional[str] = None) -> list[Appointment]: ...
    def update(self, appointment: Appointment) -> None: ...


@dataclass
class InMemoryAppointmentStore:
    """Process-local default. Multi-worker hosts must inject a shared adapter."""

    hosts: dict[str, Host] = field(default_factory=dict)
    appointments: dict[str, Appointment] = field(default_factory=dict)

    def list_hosts(self) -> list[Host]:
        return list(self.hosts.values())

    def get_host(self, host_id: str) -> Optional[Host]:
        return self.hosts.get(host_id)

    def booked_times(self, host_id: str, date: str) -> set[str]:
        return {a.time for a in self.appointments.values()
                if a.host_id == host_id and a.date == date and a.status == "booked"}

    def add(self, appointment: Appointment) -> None:
        self.appointments[appointment.appointment_id] = appointment

    def get(self, appointment_id: str) -> Optional[Appointment]:
        return self.appointments.get(appointment_id)

    def list(self, *, host_id: Optional[str] = None,
             with_name: Optional[str] = None) -> list[Appointment]:
        out = list(self.appointments.values())
        if host_id is not None:
            out = [a for a in out if a.host_id == host_id]
        if with_name is not None:
            out = [a for a in out if a.with_name.lower() == with_name.lower()]
        return out

    def update(self, appointment: Appointment) -> None:
        self.appointments[appointment.appointment_id] = appointment
