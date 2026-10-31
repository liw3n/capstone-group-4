"""PostgreSQL source of truth for synthetic CRM contacts."""
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app import config
from app.campaigns.repository import RequestScope, _storage_tenant_id


class ContactStorageUnavailable(RuntimeError):
    """Safe public error for contact storage failures."""


@contextmanager
def _connection() -> Iterator[Any]:
    database_url = config.get_settings().database_url
    if not database_url:
        raise ContactStorageUnavailable("Contact database is not configured")
    try:
        with psycopg.connect(
            database_url, row_factory=dict_row, connect_timeout=5
        ) as connection:
            connection.execute("SET LOCAL statement_timeout = '5s'")
            yield connection
    except psycopg.Error as exc:
        raise ContactStorageUnavailable(
            "Contact database is temporarily unavailable"
        ) from exc


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _record(
    row: dict[str, Any],
    gender: dict[str, str | None],
    cash: dict[str, float | None],
) -> dict[str, Any]:
    extra = dict()
    extra.update({
        "id": row["contact_id"],
        "name": row["full_name"],
        "email": row.get("email"),
        "phone": f"{row.get('mobile_country_code', '+65')} {row['mobile']}",
        "dob": row["date_of_birth"].isoformat() if row["date_of_birth"] else None,
        "gender": gender.get(row["contact_id"]),
        "cashAmount": _number(cash.get(row["contact_id"])),
        "label": row["contact_type"],
        "optInEmail": row["opt_in_email"],
    })
    return extra


SELECT_COLUMNS = """
    contact_id, full_name, email, mobile, mobile_country_code, date_of_birth, contact_type, opt_in_email
"""


def list_contacts(scope: RequestScope) -> list[dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            f"""SELECT {SELECT_COLUMNS}
                FROM contact
                WHERE tenant_id = %s AND is_deleted = FALSE
                  AND (assigned_to_user_id = %s OR
                       (assigned_to_user_id IS NULL AND created_by_user_id = %s))
                ORDER BY contact_id""",
            (_storage_tenant_id(scope), scope.fa_id, scope.fa_id),
        ).fetchall()
    gender, cash = _call_mock_portfolio_api([row["contact_id"] for row in rows])
    return [_record(row, gender, cash) for row in rows]

def _call_mock_portfolio_api(contact_ids: list[str]) -> tuple[dict[str, str], dict[str, float]]:
    """
    Mock function to simulate calling an internal GWM API.
    Returns a tuple of two dictionaries:
    - gender_map: mapping contact_id to gender
    - cash_map: mapping contact_id to available_cash
    """
    # For demonstration purposes, we will return dummy data.
    gender_map = {contact_id: "Male" if i % 2 == 0 else "Female" for i, contact_id in enumerate(contact_ids)}
    cash_map = {contact_id: 10000.0 + i * 5000.0 for i, contact_id in enumerate(contact_ids)}
    return gender_map, cash_map


def _crm_data(payload: dict[str, Any]) -> dict[str, Any]:
    scalar_fields = {
        "id", "name", "email", "countryCode", "phone", "dob", "gender",
        "cashAmount", "label", "status", "bookmarked", "needsAttention",
        "optInEmail", "optInSms",
    }
    return {key: value for key, value in payload.items()
            if key not in scalar_fields and value is not None}


def create_contact(scope: RequestScope, payload: dict[str, Any]) -> dict[str, Any]:
    with _connection() as connection:
        if connection.execute(
            "SELECT 1 FROM contact WHERE tenant_id = %s AND contact_id = %s",
            (_storage_tenant_id(scope), payload["id"]),
        ).fetchone():
            raise ValueError("Contact ID already exists")
        row = connection.execute(
            f"""
            INSERT INTO contact (
                tenant_id, contact_id, contact_type, full_name, email, mobile,
                mobile_country_code, date_of_birth, nric_passport_no, created_by_user_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            RETURNING {SELECT_COLUMNS}
            """,
            (
                _storage_tenant_id(scope), payload["id"], payload.get("label", "Prospect"),
                payload["name"], payload["email"], payload["phone"], payload["countryCode"],
                payload.get("dob"), payload.get("nric"), scope.fa_id,
            ),
        ).fetchone()
    if row is None:
        raise ContactStorageUnavailable("Created contact could not be retrieved")
    contact_id = str(row["contact_id"])
    gender = {contact_id: payload.get("gender")}
    cash = {contact_id: payload.get("cashAmount")}
    return {**_record(row, gender, cash), **payload}


def replace_contact(scope: RequestScope, contact_id: str,
                    payload: dict[str, Any]) -> dict[str, Any] | None:
    with _connection() as connection:
        updated = connection.execute(
            """
            UPDATE contact
            SET full_name = %s, email = %s, mobile_country_code = %s, mobile = %s,
                date_of_birth = %s, contact_type = COALESCE(%s, contact_type), opt_in_email = %s
            WHERE tenant_id = %s AND contact_id = %s AND is_deleted = FALSE
              AND (assigned_to_user_id = %s OR
                   (assigned_to_user_id IS NULL AND created_by_user_id = %s))
            """,
            (
                payload["name"], payload["email"], payload["countryCode"],
                payload["phone"], payload.get("dob"), payload.get("label"),
                payload.get("optInEmail", False), _storage_tenant_id(scope),
                contact_id, scope.fa_id, scope.fa_id,
            ),
        )
        if updated.rowcount == 0:
            return None
        row = connection.execute(
            f"""SELECT {SELECT_COLUMNS} FROM contact
                WHERE tenant_id = %s AND contact_id = %s AND is_deleted = FALSE
                  AND (assigned_to_user_id = %s OR
                       (assigned_to_user_id IS NULL AND created_by_user_id = %s))""",
            (_storage_tenant_id(scope), contact_id, scope.fa_id, scope.fa_id),
        ).fetchone()
    if row is None:
        raise ContactStorageUnavailable("Updated contact could not be retrieved")
    return _record(row, {}, {})
