"""Postgres ``AppointmentStore`` adapter (psycopg 3).

Follows the ecosystem data standard (see cogno-host DATA_MODEL.md): every row carries the
opaque ``scope`` the host composes, and the high-volume ``appointments`` table is
**``PARTITION BY HASH(scope)``** over N buckets (engram's pattern — zero DDL per tenant).
The scheduler is single-tenant-per-instance, so the adapter is **bound to one scope** at
construction and stamps/filters it on every row; the ``AppointmentStore`` Protocol stays
scope-free. ``pip install cogno-praxis[postgres]``.
"""

from __future__ import annotations

from typing import Optional

import psycopg

from cogno_praxis.scheduler.store import ACTIVE_STATUS, Appointment, Host

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
               PRIMARY KEY (appointment_id, scope)
           ) PARTITION BY HASH (scope)""")
    for k in range(partitions):
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS appointments_p{k} PARTITION OF appointments "
            f"FOR VALUES WITH (MODULUS {partitions}, REMAINDER {k})")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_appt_scope_host_date "
        "ON appointments (scope, host_id, date)")


def _host(row: tuple) -> Host:
    return Host(host_id=row[0], name=row[1], role=row[2], auto_confirm=row[3])


def _appt(row: tuple) -> Appointment:
    return Appointment(appointment_id=row[0], host_id=row[1], date=row[2], time=row[3],
                       with_name=row[4], status=row[5], cancel_reason=row[6], notes=row[7])


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
        self._conn.execute(
            """INSERT INTO appointments (appointment_id, scope, host_id, date, time,
                   with_name, status, cancel_reason, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (a.appointment_id, self._scope, a.host_id, a.date, a.time, a.with_name,
             a.status, a.cancel_reason, a.notes))

    def get(self, appointment_id: str) -> Optional[Appointment]:
        row = self._conn.execute(
            "SELECT appointment_id, host_id, date, time, with_name, status, cancel_reason, "
            "notes FROM appointments WHERE scope = %s AND appointment_id = %s",
            (self._scope, appointment_id)).fetchone()
        return _appt(row) if row else None

    def list(self, *, host_id: Optional[str] = None,
             with_name: Optional[str] = None) -> list[Appointment]:
        sql = ("SELECT appointment_id, host_id, date, time, with_name, status, "
               "cancel_reason, notes FROM appointments WHERE scope = %s")
        params: list = [self._scope]
        if host_id is not None:
            sql += " AND host_id = %s"
            params.append(host_id)
        if with_name is not None:
            sql += " AND lower(with_name) = lower(%s)"
            params.append(with_name)
        sql += " ORDER BY date, time"
        return [_appt(r) for r in self._conn.execute(sql, params).fetchall()]

    def update(self, appointment: Appointment) -> None:
        a = appointment
        self._conn.execute(
            """UPDATE appointments SET host_id = %s, date = %s, time = %s, with_name = %s,
                   status = %s, cancel_reason = %s, notes = %s
               WHERE scope = %s AND appointment_id = %s""",
            (a.host_id, a.date, a.time, a.with_name, a.status, a.cancel_reason, a.notes,
             self._scope, a.appointment_id))
