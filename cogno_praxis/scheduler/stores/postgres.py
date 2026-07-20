"""Postgres ``AppointmentStore`` adapter (psycopg 3).

Follows the ecosystem data standard (see cogno-host DATA_MODEL.md): every row carries the
opaque ``scope`` the host composes, and the high-volume ``appointments`` table is
**``PARTITION BY HASH(scope)``** over N buckets (engram's pattern — zero DDL per tenant).
The scheduler is single-tenant-per-instance, so the adapter is **bound to one scope** at
construction and stamps/filters it on every row; the ``AppointmentStore`` Protocol stays
scope-free. ``pip install cogno-praxis[postgres]``.
"""

from __future__ import annotations

import logging
from typing import Optional

import psycopg

from cogno_praxis.scheduler.store import ACTIVE_STATUS, Appointment, Host, SlotTakenError

logger = logging.getLogger(__name__)

_ACTIVE = tuple(ACTIVE_STATUS)


def _ensure_schema(conn: "psycopg.Connection", partitions: int) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schedule_hosts (
               scope text NOT NULL, host_id text NOT NULL, name text NOT NULL,
               role text NOT NULL DEFAULT '', auto_confirm boolean NOT NULL DEFAULT true,
               PRIMARY KEY (scope, host_id))""")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS appointments (
               appointment_id text NOT NULL, scope text NOT NULL, host_id text NOT NULL,
               date text NOT NULL, time text NOT NULL, with_name text NOT NULL,
               status text NOT NULL, cancel_reason text NOT NULL DEFAULT '',
               notes text NOT NULL DEFAULT '',
               guest_id text NOT NULL DEFAULT '', host_name text NOT NULL DEFAULT '',
               PRIMARY KEY (appointment_id, scope)
           ) PARTITION BY HASH (scope)""")
    # Migration-safe: add the two-sided-identity columns to a pre-existing table.
    conn.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS guest_id text NOT NULL DEFAULT ''")
    conn.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS host_name text NOT NULL DEFAULT ''")
    for k in range(partitions):
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS appointments_p{k} PARTITION OF appointments "
            f"FOR VALUES WITH (MODULUS {partitions}, REMAINDER {k})")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_appt_scope_host_date "
        "ON appointments (scope, host_id, date)")
    _ensure_slot_uniqueness(conn)
    # The guest-side visibility query (a GUEST's own bookings) is keyed by (scope, guest_id).
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_appt_scope_guest "
        "ON appointments (scope, guest_id)")


def _host(row: tuple) -> Host:
    return Host(host_id=row[0], name=row[1], role=row[2], auto_confirm=row[3])


# The canonical column order for an appointment SELECT (kept in sync with ``_appt``).
_APPT_COLS = ("appointment_id, host_id, date, time, with_name, status, cancel_reason, "
              "notes, guest_id, host_name")


def _ensure_slot_uniqueness(conn: "psycopg.Connection") -> None:
    """The atomic guard against double-booking.

    ``book()`` is check-then-insert: it reads ``booked_times`` and then inserts. Two turns for
    the same tenant run concurrently (host locks are per-SESSION, and the scheduler's sync MCP
    tools are dispatched from a threadpool), so both can pass the check and insert the same
    slot. Only a constraint closes that window.

    PARTIAL by design — it must cover only the statuses that still occupy a slot, so
    cancel→rebook and the pile of CANCELED/COMPLETED history rows on a slot stay legal.
    ``scope`` leads the column list because Postgres requires a unique index on a partitioned
    table to contain the partition key.

    Creation FAILS if the table already holds conflicting active rows. That must not take the
    whole scheduler down at import time, so we log the conflict and carry on with the
    service-level pre-check as the only guard (the pre-existing behaviour) — the operator gets
    an actionable warning naming the query that finds the offenders."""
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_appt_active_slot "
            "ON appointments (scope, host_id, date, time) "
            f"WHERE status IN {_ACTIVE}")
    except psycopg.errors.UniqueViolation:
        logger.warning(
            "stage=scheduler event=slot_uniqueness_unavailable reason=duplicate_active_rows "
            "action=%s",
            "SELECT scope,host_id,date,time,count(*) FROM appointments "
            f"WHERE status IN {_ACTIVE} GROUP BY 1,2,3,4 HAVING count(*)>1")


def _appt(row: tuple) -> Appointment:
    return Appointment(appointment_id=row[0], host_id=row[1], date=row[2], time=row[3],
                       with_name=row[4], status=row[5], cancel_reason=row[6], notes=row[7],
                       guest_id=row[8], host_name=row[9])


class PgAppointmentStore:
    """A psycopg-backed ``AppointmentStore`` bound to one ``scope`` (the tenant)."""

    def __init__(self, dsn: str, scope: str, *, partitions: int = 8) -> None:
        if not scope or not scope.strip():
            raise ValueError("scope must be a non-empty string")
        self._scope = scope
        self._conn = psycopg.connect(dsn, autocommit=True)
        _ensure_schema(self._conn, partitions)

    def close(self) -> None:
        self._conn.close()

    # ── hosts (seed/admin — outside the read/write Protocol) ────────────
    def add_host(self, host: Host) -> None:
        self._conn.execute(
            """INSERT INTO schedule_hosts (scope, host_id, name, role, auto_confirm)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (scope, host_id) DO UPDATE
               SET name = EXCLUDED.name, role = EXCLUDED.role,
                   auto_confirm = EXCLUDED.auto_confirm""",
            (self._scope, host.host_id, host.name, host.role, host.auto_confirm))

    def purge_identity(self, identity_id: str) -> int:
        """Remove every scheduler row tied to a deleted identity (host side, guest side and
        the bookable-catalog entry). Returns the number of appointments removed.

        The parent enforced this with FKs + an explicit ``DELETE FROM schedule.appointments
        WHERE host_identity_id = X OR guest_identity_id = X`` inside ``delete_identity``; here
        the identities table belongs to the HOST's schema (possibly another database), so no
        cross-schema FK can exist — the host calls this on identity deletion instead. Without
        it, a deleted professional's appointments linger and resurface the moment the same
        channel id is ever re-registered (live: a re-onboarded contact promoted to EMPLOYEE
        inherited a week of old test bookings)."""
        if not identity_id:
            return 0
        cur = self._conn.execute(
            "DELETE FROM appointments WHERE scope = %s AND (host_id = %s OR guest_id = %s)",
            (self._scope, identity_id, identity_id))
        self._conn.execute(
            "DELETE FROM schedule_hosts WHERE scope = %s AND host_id = %s",
            (self._scope, identity_id))
        return cur.rowcount or 0

    def sync_hosts(self, hosts: "list[Host]") -> None:
        """Make the scope's catalog EXACTLY ``hosts``: upsert each and delete the rest.

        Used when the injected tenant catalog (``COGNO_SCHEDULER_HOSTS``) is authoritative —
        a professional removed on the dashboard must stop being offered/bookable, not linger
        from an old seed (upsert-only left ghost doctors in the catalog). Appointments keep
        their ``host_id`` (history is preserved); only the bookable catalog shrinks."""
        for h in hosts:
            self.add_host(h)
        keep = [h.host_id for h in hosts]
        if keep:
            self._conn.execute(
                "DELETE FROM schedule_hosts WHERE scope = %s AND NOT (host_id = ANY(%s))",
                (self._scope, keep))
        else:
            self._conn.execute("DELETE FROM schedule_hosts WHERE scope = %s", (self._scope,))

    def list_hosts(self) -> list[Host]:
        rows = self._conn.execute(
            "SELECT host_id, name, role, auto_confirm FROM schedule_hosts "
            "WHERE scope = %s ORDER BY host_id", (self._scope,)).fetchall()
        return [_host(r) for r in rows]

    def get_host(self, host_id: str) -> Optional[Host]:
        row = self._conn.execute(
            "SELECT host_id, name, role, auto_confirm FROM schedule_hosts "
            "WHERE scope = %s AND host_id = %s", (self._scope, host_id)).fetchone()
        return _host(row) if row else None

    # ── appointments ───────────────────────────────────────────────────
    def booked_times(self, host_id: str, date: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT time FROM appointments WHERE scope = %s AND host_id = %s "
            "AND date = %s AND status = ANY(%s)",
            (self._scope, host_id, date, list(_ACTIVE))).fetchall()
        return {r[0] for r in rows}

    def add(self, appointment: Appointment) -> None:
        a = appointment
        try:
            self._conn.execute(
                """INSERT INTO appointments (appointment_id, scope, host_id, date, time,
                       with_name, status, cancel_reason, notes, guest_id, host_name)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (a.appointment_id, self._scope, a.host_id, a.date, a.time, a.with_name,
                 a.status, a.cancel_reason, a.notes, a.guest_id, a.host_name))
        except psycopg.errors.UniqueViolation as exc:
            # ux_appt_active_slot rejected it: a concurrent turn took this slot after the
            # caller's availability check. Surface the domain error, not the driver's.
            raise SlotTakenError(
                f"{a.time} on {a.date} is already booked for {a.host_id}") from exc

    def get(self, appointment_id: str) -> Optional[Appointment]:
        row = self._conn.execute(
            f"SELECT {_APPT_COLS} FROM appointments WHERE scope = %s AND appointment_id = %s",
            (self._scope, appointment_id)).fetchone()
        return _appt(row) if row else None

    def list(self, *, host_id: Optional[str] = None, guest_id: Optional[str] = None,
             with_name: Optional[str] = None) -> list[Appointment]:
        sql = f"SELECT {_APPT_COLS} FROM appointments WHERE scope = %s"
        params: list = [self._scope]
        if host_id is not None:
            sql += " AND host_id = %s"
            params.append(host_id)
        if guest_id is not None:
            sql += " AND guest_id = %s"
            params.append(guest_id)
        if with_name is not None:
            sql += " AND lower(with_name) = lower(%s)"
            params.append(with_name)
        sql += " ORDER BY date, time"
        return [_appt(r) for r in self._conn.execute(sql, params).fetchall()]

    def update(self, appointment: Appointment) -> None:
        a = appointment
        self._conn.execute(
            """UPDATE appointments SET host_id = %s, date = %s, time = %s, with_name = %s,
                   status = %s, cancel_reason = %s, notes = %s, guest_id = %s, host_name = %s
               WHERE scope = %s AND appointment_id = %s""",
            (a.host_id, a.date, a.time, a.with_name, a.status, a.cancel_reason, a.notes,
             a.guest_id, a.host_name, self._scope, a.appointment_id))
