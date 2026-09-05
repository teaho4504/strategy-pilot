from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from trading_engine.risk.capital_allocator import (
    CapitalAllocationDecision,
    CapitalAllocationState,
)


ACTIVE_RESERVATION_STATUSES = ("reserved", "submitted", "filled")
PENDING_RESERVATION_STATUSES = ("reserved", "submitted")


@dataclass(frozen=True, slots=True)
class AllocationCycle:
    id: int
    account_scope: str
    market_date: str
    cycle_capital: float
    currency: str


@dataclass(frozen=True, slots=True)
class AllocationReservation:
    id: int
    cycle_id: int
    strategy: str
    symbol: str
    exchange: str
    tranche: int
    quantity: int
    reference_price: float
    reserved_notional: float
    status: str
    order_no: str | None
    filled_quantity: int
    last_broker_status: str | None
    submitted_at: str | None
    last_reconciled_at: str | None
    reconcile_result: str | None
    reconcile_attempts: int
    closed_at: str | None


@dataclass(frozen=True, slots=True)
class AllocationBrokerEvent:
    event_key: str
    tr_id: str
    order_no: str
    original_order_no: str | None
    symbol: str
    side: str
    status: str
    fill_quantity: int
    unfilled_quantity: int | None


@dataclass(frozen=True, slots=True)
class AllocationEventApplyResult:
    outcome: str
    reservation_id: int | None
    reservation_status: str | None
    filled_quantity: int


class CapitalAllocationStore:
    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

    def ensure_cycle(
        self,
        *,
        account_scope: str,
        market_date: str,
        orderable_cash: float,
        currency: str = "USD",
    ) -> AllocationCycle:
        clean_scope = _required_text(account_scope, "account_scope")
        clean_date = _required_text(market_date, "market_date")
        clean_currency = _required_text(currency, "currency").upper()[:8]
        if orderable_cash < 0:
            raise ValueError("orderable_cash cannot be negative")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE us_capital_allocation_cycles
                SET status = 'closed', updated_at = ?
                WHERE account_scope = ?
                  AND market_date != ?
                  AND status = 'active'
                """,
                (_now_iso(), clean_scope, clean_date),
            )
            row = connection.execute(
                """
                SELECT *
                FROM us_capital_allocation_cycles
                WHERE account_scope = ?
                  AND market_date = ?
                  AND status = 'active'
                LIMIT 1
                """,
                (clean_scope, clean_date),
            ).fetchone()
            if row is None:
                cursor = connection.execute(
                    """
                    INSERT INTO us_capital_allocation_cycles(
                      account_scope, market_date, cycle_capital, currency,
                      status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        clean_scope,
                        clean_date,
                        round(orderable_cash, 4),
                        clean_currency,
                        _now_iso(),
                        _now_iso(),
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM us_capital_allocation_cycles WHERE id = ?",
                    (int(cursor.lastrowid),),
                ).fetchone()
            connection.commit()
            return _cycle_from_row(row)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def find_cycle(
        self,
        *,
        account_scope: str,
        market_date: str,
    ) -> AllocationCycle | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM us_capital_allocation_cycles
                WHERE account_scope = ?
                  AND market_date = ?
                  AND status = 'active'
                LIMIT 1
                """,
                (
                    _required_text(account_scope, "account_scope"),
                    _required_text(market_date, "market_date"),
                ),
            ).fetchone()
        finally:
            connection.close()
        return _cycle_from_row(row) if row is not None else None

    def load_state(
        self,
        *,
        cycle: AllocationCycle,
        orderable_cash: float,
    ) -> CapitalAllocationState:
        if orderable_cash < 0:
            raise ValueError("orderable_cash cannot be negative")
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM us_capital_allocation_reservations
                WHERE cycle_id = ?
                  AND status IN ('reserved', 'submitted', 'filled')
                ORDER BY id
                """,
                (cycle.id,),
            ).fetchall()
        finally:
            connection.close()

        open_symbols = frozenset(str(row["symbol"]) for row in rows)
        pending_symbols = frozenset(
            str(row["symbol"])
            for row in rows
            if str(row["status"]) in PENDING_RESERVATION_STATUSES
        )
        filled_tranches: dict[str, int] = {}
        reserved_cash = 0.0
        for row in rows:
            status = str(row["status"])
            symbol = str(row["symbol"])
            if status in PENDING_RESERVATION_STATUSES:
                reserved_cash += float(row["reserved_notional"])
            elif status == "filled":
                filled_tranches[symbol] = filled_tranches.get(symbol, 0) + 1

        return CapitalAllocationState(
            cycle_capital=cycle.cycle_capital,
            orderable_cash=orderable_cash,
            reserved_cash=round(reserved_cash, 4),
            open_symbols=open_symbols,
            filled_tranches=filled_tranches,
            pending_symbols=pending_symbols,
        )

    def reserve(
        self,
        *,
        cycle: AllocationCycle,
        decision: CapitalAllocationDecision,
        strategy: str,
        exchange: str,
        reference_price: float,
    ) -> AllocationReservation:
        if not decision.allowed or decision.tranche is None:
            raise ValueError("allocation decision must be allowed")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT INTO us_capital_allocation_reservations(
                  cycle_id, strategy, symbol, exchange, tranche, quantity,
                  reference_price, reserved_notional, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?)
                """,
                (
                    cycle.id,
                    _required_text(strategy, "strategy")[:120],
                    decision.symbol,
                    _required_text(exchange, "exchange").upper()[:4],
                    decision.tranche,
                    decision.quantity,
                    round(reference_price, 4),
                    decision.estimated_notional,
                    _now_iso(),
                    _now_iso(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM us_capital_allocation_reservations WHERE id = ?",
                (int(cursor.lastrowid),),
            ).fetchone()
            connection.commit()
            return _reservation_from_row(row)
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise ValueError("allocation tranche is already reserved") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_submitted(self, reservation_id: int, order_no: str | None) -> None:
        self._update_status(
            reservation_id,
            from_statuses=("reserved",),
            status="submitted",
            order_no=order_no,
        )

    def record_reconciliation_result(
        self,
        reservation_id: int,
        result: str,
    ) -> None:
        self.resolve_submitted_reconciliation(
            reservation_id,
            result=result,
        )

    def resolve_submitted_reconciliation(
        self,
        reservation_id: int,
        *,
        result: str,
        terminal_status: str | None = None,
        filled_quantity: int | None = None,
        broker_status: str | None = None,
    ) -> None:
        clean_result = _reconciliation_result(result)
        if terminal_status not in {None, "filled", "released"}:
            raise ValueError("unsupported terminal allocation status")
        if filled_quantity is not None and filled_quantity < 0:
            raise ValueError("filled_quantity cannot be negative")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT quantity, filled_quantity
                FROM us_capital_allocation_reservations
                WHERE id = ?
                  AND status = 'submitted'
                LIMIT 1
                """,
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise ValueError(
                    "submitted allocation reservation is required"
                )
            resolved_quantity = int(row["filled_quantity"] or 0)
            if filled_quantity is not None:
                resolved_quantity = max(
                    resolved_quantity,
                    min(int(filled_quantity), int(row["quantity"])),
                )
            if terminal_status == "filled" and resolved_quantity <= 0:
                raise ValueError(
                    "filled terminal status requires a positive fill quantity"
                )
            if terminal_status == "released" and resolved_quantity > 0:
                raise ValueError(
                    "released terminal status cannot contain a fill quantity"
                )

            cursor = connection.execute(
                """
                UPDATE us_capital_allocation_reservations
                SET status = COALESCE(?, status),
                    filled_quantity = ?,
                    last_broker_status = COALESCE(?, last_broker_status),
                    last_reconciled_at = ?,
                    reconcile_result = ?,
                    reconcile_attempts = reconcile_attempts + 1,
                    updated_at = ?
                WHERE id = ?
                  AND status = 'submitted'
                """,
                (
                    terminal_status,
                    resolved_quantity,
                    _optional_text(broker_status),
                    _now_iso(),
                    clean_result,
                    _now_iso(),
                    reservation_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError(
                    "submitted allocation reservation is required"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_filled(self, reservation_id: int) -> None:
        self._update_status(
            reservation_id,
            from_statuses=("submitted",),
            status="filled",
            fill_to_order_quantity=True,
        )

    def close_filled(self, reservation_id: int) -> bool:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status
                FROM us_capital_allocation_reservations
                WHERE id = ?
                LIMIT 1
                """,
                (reservation_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                return False
            if str(row["status"]) == "closed":
                connection.rollback()
                return True
            if str(row["status"]) != "filled":
                connection.rollback()
                return False
            closed_at = _now_iso()
            connection.execute(
                """
                UPDATE us_capital_allocation_reservations
                SET status = 'closed',
                    closed_at = COALESCE(closed_at, ?),
                    updated_at = ?
                WHERE id = ?
                  AND status = 'filled'
                """,
                (closed_at, closed_at, reservation_id),
            )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def release(self, reservation_id: int) -> None:
        self._update_status(
            reservation_id,
            from_statuses=("reserved", "submitted"),
            status="released",
        )

    def list_reservations(self, cycle_id: int) -> list[AllocationReservation]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT *
                FROM us_capital_allocation_reservations
                WHERE cycle_id = ?
                ORDER BY id
                """,
                (cycle_id,),
            ).fetchall()
        finally:
            connection.close()
        return [_reservation_from_row(row) for row in rows]

    def find_by_order_no(
        self,
        *,
        order_no: str,
        symbol: str,
        exchange: str,
    ) -> AllocationReservation | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT *
                FROM us_capital_allocation_reservations
                WHERE order_no = ?
                  AND UPPER(symbol) = UPPER(?)
                  AND UPPER(exchange) = UPPER(?)
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    _required_text(order_no, "order_no"),
                    _required_text(symbol, "symbol"),
                    _required_text(exchange, "exchange"),
                ),
            ).fetchone()
        finally:
            connection.close()
        return _reservation_from_row(row) if row is not None else None

    def apply_broker_event(
        self,
        *,
        cycle: AllocationCycle,
        event: AllocationBrokerEvent,
    ) -> AllocationEventApplyResult:
        if event.side != "buy":
            return AllocationEventApplyResult("ignored_side", None, None, 0)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            event_key = _required_text(event.event_key, "event_key")
            existing_event = connection.execute(
                """
                SELECT
                  event.reservation_id,
                  reservation.status,
                  reservation.filled_quantity
                FROM us_capital_allocation_events AS event
                LEFT JOIN us_capital_allocation_reservations AS reservation
                  ON reservation.id = event.reservation_id
                WHERE event.cycle_id = ?
                  AND event.event_key = ?
                LIMIT 1
                """,
                (cycle.id, event_key),
            ).fetchone()
            if existing_event is not None:
                connection.rollback()
                return AllocationEventApplyResult(
                    "duplicate",
                    int(existing_event["reservation_id"]),
                    _optional_text(existing_event["status"]),
                    int(existing_event["filled_quantity"] or 0),
                )

            order_numbers = tuple(
                value
                for value in (event.order_no, event.original_order_no)
                if value
            )
            placeholders = ",".join("?" for _ in order_numbers)
            row = connection.execute(
                f"""
                SELECT *
                FROM us_capital_allocation_reservations
                WHERE cycle_id = ?
                  AND status = 'submitted'
                  AND UPPER(symbol) = UPPER(?)
                  AND order_no IN ({placeholders})
                ORDER BY id
                LIMIT 1
                """,
                (cycle.id, event.symbol, *order_numbers),
            ).fetchone()
            if row is None:
                connection.rollback()
                return AllocationEventApplyResult("unmatched", None, None, 0)

            inserted = connection.execute(
                """
                INSERT OR IGNORE INTO us_capital_allocation_events(
                  cycle_id, reservation_id, event_key, tr_id, order_no,
                  symbol, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle.id,
                    int(row["id"]),
                    event_key,
                    _required_text(event.tr_id, "tr_id"),
                    _required_text(event.order_no, "order_no"),
                    _required_text(event.symbol, "symbol").upper()[:12],
                    _required_text(event.status, "status")[:80],
                    _now_iso(),
                ),
            )
            if inserted.rowcount != 1:
                connection.rollback()
                return AllocationEventApplyResult(
                    "duplicate",
                    int(row["id"]),
                    str(row["status"]),
                    int(row["filled_quantity"] or 0),
                )

            current_filled = int(row["filled_quantity"] or 0)
            filled_quantity = min(
                int(row["quantity"]),
                current_filled + max(0, event.fill_quantity),
            )
            status = str(row["status"])
            normalized_status = event.status.replace(" ", "")
            terminal_rejection = any(
                marker in normalized_status
                for marker in ("무효", "거부", "실패")
            )
            terminal_cancellation = (
                "취소" in normalized_status
                and not any(
                    marker in normalized_status
                    for marker in ("전송", "접수", "요청")
                )
            )
            complete_fill = filled_quantity > 0 and (
                filled_quantity >= int(row["quantity"])
                or event.unfilled_quantity == 0
                or "체결완료" in normalized_status
            )

            if complete_fill:
                status = "filled"
            elif terminal_rejection or terminal_cancellation:
                status = "filled" if filled_quantity > 0 else "released"

            connection.execute(
                """
                UPDATE us_capital_allocation_reservations
                SET status = ?,
                    filled_quantity = ?,
                    last_broker_status = ?,
                    updated_at = ?
                WHERE id = ?
                  AND status = 'submitted'
                """,
                (
                    status,
                    filled_quantity,
                    event.status[:80],
                    _now_iso(),
                    int(row["id"]),
                ),
            )
            connection.commit()
            return AllocationEventApplyResult(
                "updated",
                int(row["id"]),
                status,
                filled_quantity,
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _update_status(
        self,
        reservation_id: int,
        *,
        from_statuses: tuple[str, ...],
        status: str,
        order_no: str | None = None,
        fill_to_order_quantity: bool = False,
    ) -> None:
        placeholders = ",".join("?" for _ in from_statuses)
        connection = self._connect()
        try:
            updated_at = _now_iso()
            cursor = connection.execute(
                f"""
                UPDATE us_capital_allocation_reservations
                SET status = ?,
                    order_no = COALESCE(?, order_no),
                    submitted_at = CASE
                      WHEN ? = 'submitted'
                      THEN COALESCE(submitted_at, ?)
                      ELSE submitted_at
                    END,
                    filled_quantity = CASE
                      WHEN ? THEN quantity
                      ELSE filled_quantity
                    END,
                    updated_at = ?
                WHERE id = ?
                  AND status IN ({placeholders})
                """,
                (
                    status,
                    _optional_text(order_no),
                    status,
                    updated_at,
                    int(fill_to_order_quantity),
                    updated_at,
                    reservation_id,
                    *from_statuses,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("allocation reservation state transition is invalid")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS us_capital_allocation_cycles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              account_scope TEXT NOT NULL,
              market_date TEXT NOT NULL,
              cycle_capital REAL NOT NULL,
              currency TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_us_capital_cycle_active
            ON us_capital_allocation_cycles(account_scope, market_date)
            WHERE status = 'active';

            CREATE TABLE IF NOT EXISTS us_capital_allocation_reservations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              cycle_id INTEGER NOT NULL,
              strategy TEXT NOT NULL,
              symbol TEXT NOT NULL,
              exchange TEXT NOT NULL,
              tranche INTEGER NOT NULL,
              quantity INTEGER NOT NULL,
              reference_price REAL NOT NULL,
                  reserved_notional REAL NOT NULL,
                  status TEXT NOT NULL,
                  order_no TEXT,
                  filled_quantity INTEGER NOT NULL DEFAULT 0,
                  last_broker_status TEXT,
                  submitted_at TEXT,
                  last_reconciled_at TEXT,
                  reconcile_result TEXT,
                  reconcile_attempts INTEGER NOT NULL DEFAULT 0,
                  closed_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
              FOREIGN KEY(cycle_id) REFERENCES us_capital_allocation_cycles(id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_us_capital_symbol_tranche
            ON us_capital_allocation_reservations(cycle_id, symbol, tranche);

            CREATE TABLE IF NOT EXISTS us_capital_allocation_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              cycle_id INTEGER NOT NULL,
              reservation_id INTEGER NOT NULL,
              event_key TEXT NOT NULL,
              tr_id TEXT NOT NULL,
              order_no TEXT NOT NULL,
              symbol TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY(cycle_id) REFERENCES us_capital_allocation_cycles(id),
              FOREIGN KEY(reservation_id)
                REFERENCES us_capital_allocation_reservations(id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_us_capital_event_key
            ON us_capital_allocation_events(cycle_id, event_key);
            """
        )
        reservation_columns = {
            str(row["name"])
            for row in connection.execute(
                "PRAGMA table_info(us_capital_allocation_reservations)"
            ).fetchall()
        }
        if "filled_quantity" not in reservation_columns:
            connection.execute(
                """
                ALTER TABLE us_capital_allocation_reservations
                ADD COLUMN filled_quantity INTEGER NOT NULL DEFAULT 0
                """
            )
        if "last_broker_status" not in reservation_columns:
            connection.execute(
                """
                ALTER TABLE us_capital_allocation_reservations
                ADD COLUMN last_broker_status TEXT
                """
            )
        if "submitted_at" not in reservation_columns:
            connection.execute(
                """
                ALTER TABLE us_capital_allocation_reservations
                ADD COLUMN submitted_at TEXT
                """
            )
        if "last_reconciled_at" not in reservation_columns:
            connection.execute(
                """
                ALTER TABLE us_capital_allocation_reservations
                ADD COLUMN last_reconciled_at TEXT
                """
            )
        if "reconcile_result" not in reservation_columns:
            connection.execute(
                """
                ALTER TABLE us_capital_allocation_reservations
                ADD COLUMN reconcile_result TEXT
                """
            )
        if "reconcile_attempts" not in reservation_columns:
            connection.execute(
                """
                ALTER TABLE us_capital_allocation_reservations
                ADD COLUMN reconcile_attempts INTEGER NOT NULL DEFAULT 0
                """
            )
        if "closed_at" not in reservation_columns:
            connection.execute(
                """
                ALTER TABLE us_capital_allocation_reservations
                ADD COLUMN closed_at TEXT
                """
            )
        connection.execute(
            """
            UPDATE us_capital_allocation_reservations
            SET submitted_at = updated_at
            WHERE status = 'submitted'
              AND submitted_at IS NULL
            """
        )
        connection.commit()
        return connection


def _cycle_from_row(row: sqlite3.Row | None) -> AllocationCycle:
    if row is None:
        raise RuntimeError("allocation cycle row is missing")
    return AllocationCycle(
        id=int(row["id"]),
        account_scope=str(row["account_scope"]),
        market_date=str(row["market_date"]),
        cycle_capital=float(row["cycle_capital"]),
        currency=str(row["currency"]),
    )


def _reservation_from_row(row: sqlite3.Row | None) -> AllocationReservation:
    if row is None:
        raise RuntimeError("allocation reservation row is missing")
    return AllocationReservation(
        id=int(row["id"]),
        cycle_id=int(row["cycle_id"]),
        strategy=str(row["strategy"]),
        symbol=str(row["symbol"]),
        exchange=str(row["exchange"]),
        tranche=int(row["tranche"]),
        quantity=int(row["quantity"]),
        reference_price=float(row["reference_price"]),
        reserved_notional=float(row["reserved_notional"]),
        status=str(row["status"]),
        order_no=_optional_text(row["order_no"]),
        filled_quantity=int(row["filled_quantity"] or 0),
        last_broker_status=_optional_text(row["last_broker_status"]),
        submitted_at=_optional_text(row["submitted_at"]),
        last_reconciled_at=_optional_text(row["last_reconciled_at"]),
        reconcile_result=_optional_text(row["reconcile_result"]),
        reconcile_attempts=int(row["reconcile_attempts"] or 0),
        closed_at=_optional_text(row["closed_at"]),
    )


def _required_text(value: object, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _optional_text(value: object) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _reconciliation_result(value: object) -> str:
    result = _required_text(value, "result").lower()
    if result not in {
        "fill_query_error",
        "open_query_error",
        "filled_confirmed",
        "unresolved",
        "open_pending",
        "partial_fill",
        "canceled_confirmed",
        "rejected_confirmed",
    }:
        raise ValueError("unsupported reconciliation result")
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
