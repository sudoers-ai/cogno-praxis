"""Domain types + the persistence port for the ``scheduler`` (agenda) vertical.

Appointments are **structured domain data**, not conversation memory — so the
vertical owns its own store port (the homeo pattern: a Protocol + an in-memory
default; the host plugs a real DB adapter). This keeps even the product vertical
infra-agnostic. cogno-engram stays for episodic/KG memory, not appointment rows.

The vertical is **tenant-agnostic**: multi-tenancy is the host pointing at the right
store/adapter (one instance per tenant, or a tenant-scoped DSN), never a column the
vertical filters. Identity fields are **opaque strings** — the host resolves/authorizes
them; the scheduler just persists and echoes them back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

# Appointment lifecycle (aligned with the parent SaaS scheduler module).
PENDING = "PENDING"        # booked by a guest, awaiting confirmation
CONFIRMED = "CONFIRMED"    # approved
COMPLETED = "COMPLETED"    # finished
CANCELED = "CANCELED"      # canceled by either party
VALID_STATUS: tuple[str, ...] = (PENDING, CONFIRMED, COMPLETED, CANCELED)

# Statuses that still occupy a slot (block availability). A COMPLETED/CANCELED
# appointment frees the slot for future booking.
ACTIVE_STATUS: frozenset[str] = frozenset({PENDING, CONFIRMED})

# Roles whose "my appointments" view is UNSCOPED (sees every agenda in the scope) — the
# oversight roles. EMPLOYEE sees their own host agenda; GUEST sees their own bookings.
# The vertical only maps role→visibility (mechanics); the host decides the role (authorises).
GUEST_ROLE = "GUEST"
EMPLOYEE_ROLE = "EMPLOYEE"
OVERSIGHT_ROLES: frozenset[str] = frozenset({"SUPERVISOR", "ADMIN", "SECRETARY"})


@dataclass
class Host:
    """Someone who can be booked (a professional, a room, a resource)."""

    host_id: str
    name: str
    role: str = ""
    # The professional's own choice (the parent's identities.auto_confirm_appointments):
    # True → a guest booking is CONFIRMED immediately; False → it stays PENDING until the
    # professional accepts it (update_appointment_status → CONFIRMED). Employee-controlled.
    auto_confirm: bool = True


@dataclass
class Appointment:
    appointment_id: str
    host_id: str         # the professional's STABLE id (opaque; == the host identity id)
    date: str            # ISO date "YYYY-MM-DD"
    time: str            # "HH:MM"
    with_name: str       # the client's DISPLAY name (denormalized; NOT a key — see guest_id)
    status: str = PENDING        # PENDING | CONFIRMED | COMPLETED | CANCELED
    cancel_reason: str = ""      # filled when status -> CANCELED
    notes: str = ""
    # The two-sided identity model (parent parity): both parties are STABLE opaque ids, so the
    # same row is found from either side — a guest by ``guest_id``, the professional by ``host_id``
    # — instead of the brittle display-name match ``with_name`` used to do. ``host_name`` is the
    # professional's display name, denormalized like ``with_name`` (the vertical does not own the
    # identity directory, so it can't JOIN labels — it echoes what the host injected).
    guest_id: str = ""           # the client's stable id (empty for a block / nameless hold)
    host_name: str = ""          # the professional's display name (denormalized)

    @property
    def is_block(self) -> bool:
        """A *block* (host self-occupation / "unavailable") has no client — it occupies a slot
        like any active appointment but is not a real booking. The host creates these via
        ``block_schedule``; the parent modelled them the same way (a CONFIRMED appointment with
        no guest, titled "Indisponível")."""
        return not self.guest_id.strip() and not self.with_name.strip()


@runtime_checkable
class AppointmentStore(Protocol):
    """Persistence port. The host injects a real adapter; the default is in-memory."""

    def list_hosts(self) -> list[Host]: ...
    def get_host(self, host_id: str) -> Optional[Host]: ...
    def booked_times(self, host_id: str, date: str) -> set[str]: ...
    def add(self, appointment: Appointment) -> None: ...
    def get(self, appointment_id: str) -> Optional[Appointment]: ...
    def list(self, *, host_id: Optional[str] = None, guest_id: Optional[str] = None,
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
                if a.host_id == host_id and a.date == date and a.status in ACTIVE_STATUS}

    def add(self, appointment: Appointment) -> None:
        self.appointments[appointment.appointment_id] = appointment

    def get(self, appointment_id: str) -> Optional[Appointment]:
        return self.appointments.get(appointment_id)

    def list(self, *, host_id: Optional[str] = None, guest_id: Optional[str] = None,
             with_name: Optional[str] = None) -> list[Appointment]:
        out = list(self.appointments.values())
        if host_id is not None:
            out = [a for a in out if a.host_id == host_id]
        if guest_id is not None:
            out = [a for a in out if a.guest_id == guest_id]
        if with_name is not None:
            out = [a for a in out if a.with_name.lower() == with_name.lower()]
        return out

    def update(self, appointment: Appointment) -> None:
        self.appointments[appointment.appointment_id] = appointment
