from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app import main
from app.contacts import catalog
from app.contacts.catalog import ContactStorageUnavailable
from app.campaigns.repository import RequestScope


client = TestClient(main.app)


def contact_payload(**updates):
    payload = {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "Synthetic Contact",
        "email": "synthetic.contact@example.test",
        "countryCode": "+65",
        "phone": "",
        "status": "contact",
        "bookmarked": False,
        "needsAttention": False,
        "optInEmail": False,
        "optInSms": False,
        "meetings": [],
        "policies": [],
    }
    payload.update(updates)
    return payload


def test_contact_list_passes_adviser_scope(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main,
        "list_contacts",
        lambda scope: calls.append(scope) or [contact_payload()],
    )
    response = client.get("/api/contacts", params={"fa_id": "adv-demo"})
    assert response.status_code == 200
    assert response.json()[0]["id"] == "00000000-0000-0000-0000-000000000001"
    assert calls == [RequestScope("adv-demo")]


def test_contact_list_maps_storage_failure_to_503(monkeypatch):
    def fail(_scope):
        raise ContactStorageUnavailable("Contact database is temporarily unavailable")

    monkeypatch.setattr(main, "list_contacts", fail)
    for path in ("/contacts", "/api/contacts"):
        response = client.get(path, params={"fa_id": "adv-demo"})
        assert response.status_code == 503
        assert response.json() == {
            "detail": "Contact database is temporarily unavailable"
        }


def test_contact_catalog_does_not_swallow_storage_failure(monkeypatch):
    def fail():
        raise ContactStorageUnavailable("Contact database is temporarily unavailable")

    monkeypatch.setattr(catalog, "_connection", fail)
    with pytest.raises(ContactStorageUnavailable):
        catalog.list_contacts(RequestScope("adv-demo"))


def test_contact_catalog_lists_only_records_assigned_to_or_created_by_adviser(monkeypatch):
    executed = []

    class Cursor:
        def fetchall(self):
            return []

    class Connection:
        def execute(self, query, params):
            executed.append((query, params))
            return Cursor()

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(catalog, "_connection", connection)
    assert catalog.list_contacts(RequestScope("adv-demo")) == []
    assert executed[0][1] == ("adv-demo", "adv-demo", "adv-demo")
    assert "assigned_to_user_id = %s" in executed[0][0]
    assert "created_by_user_id = %s" in executed[0][0]


def test_contact_create_is_scoped(monkeypatch):
    calls = []
    monkeypatch.setattr(
        main,
        "create_contact",
        lambda scope, payload: calls.append((scope, payload)) or payload,
    )
    response = client.post(
        "/contacts", params={"fa_id": "adv-demo"}, json=contact_payload()
    )
    assert response.status_code == 201
    assert calls[0][0] == RequestScope("adv-demo")


def test_contact_catalog_create_returns_payload_after_insert(monkeypatch):
    executed = []
    saved_row = {
        "contact_id": "00000000-0000-0000-0000-000000000001",
        "full_name": "Synthetic Contact",
        "email": "synthetic.contact@example.test",
        "mobile": "91234567",
        "date_of_birth": None,
        "contact_type": "Prospect",
        "opt_in_email": False,
    }

    class Cursor:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def execute(self, query, params):
            executed.append((query, params))
            if query.lstrip().startswith("INSERT"):
                return Cursor(saved_row)
            return Cursor()

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(catalog, "_connection", connection)
    payload = contact_payload(countryCode="+65", phone="81234567")

    result = catalog.create_contact(RequestScope("adv-demo"), payload)

    assert result["id"] == payload["id"]
    assert result["name"] == payload["name"]
    assert result["countryCode"] == "+65"
    assert result["phone"] == payload["phone"]
    insert_query, insert_params = executed[1]
    assert "RETURNING" in insert_query
    assert not insert_query.rstrip().split("VALUES", 1)[1].rstrip().endswith(",)")
    assert insert_params[:4] == (
        "adv-demo", payload["id"], "Prospect", payload["name"]
    )
    assert insert_params[5:8] == ("81234567", "+65", None)
    assert "mobile_country_code" in insert_query


def test_contact_catalog_replace_updates_existing_contact(monkeypatch):
    executed = []
    saved_row = {
        "contact_id": "00000000-0000-0000-0000-000000000001",
        "full_name": "Updated Contact",
        "email": "updated.contact@example.test",
        "mobile": "91234567",
        "mobile_country_code": "+65",
        "date_of_birth": None,
        "contact_type": "Client",
        "opt_in_email": True,
    }

    class Cursor:
        rowcount = 1

        def fetchone(self):
            return saved_row

    class Connection:
        def execute(self, query, params):
            executed.append((query, params))
            return Cursor()

    @contextmanager
    def connection():
        yield Connection()

    monkeypatch.setattr(catalog, "_connection", connection)
    payload = contact_payload(
        name="Updated Contact",
        email="updated.contact@example.test",
        phone="91234567",
        label="Client",
        optInEmail=True,
    )

    result = catalog.replace_contact(
        RequestScope("adv-demo"), payload["id"], payload
    )

    assert result is not None
    assert result["name"] == "Updated Contact"
    assert result["label"] == "Client"
    update_query, update_params = executed[0]
    assert "UPDATE contact" in update_query
    assert "opt_in_email = %s\n            WHERE" in update_query
    assert update_params[-4:] == (
        "adv-demo", payload["id"], "adv-demo", "adv-demo"
    )
    assert "assigned_to_user_id = %s" in update_query


def test_contact_replace_checks_body_and_path_ids(monkeypatch):
    monkeypatch.setattr(
        main,
        "replace_contact",
        lambda *_args: (_ for _ in ()).throw(AssertionError("storage must not be called")),
    )
    response = client.put(
        "/api/contacts/client-one",
        params={"fa_id": "adv-demo"},
        json=contact_payload(id="00000000-0000-0000-0000-000000000002"),
    )
    assert response.status_code == 400


def test_contact_replace_hides_inaccessible_records(monkeypatch):
    monkeypatch.setattr(main, "replace_contact", lambda *_args: None)
    response = client.put(
        "/api/contacts/00000000-0000-0000-0000-000000000001",
        params={"fa_id": "adv-demo"},
        json=contact_payload(),
    )
    assert response.status_code == 404


def test_contact_identifier_is_validated_before_storage(monkeypatch):
    monkeypatch.setattr(
        main,
        "replace_contact",
        lambda *_args: (_ for _ in ()).throw(AssertionError("storage must not be called")),
    )
    response = client.put(
        "/api/contacts/bad%20id",
        params={"fa_id": "adv-demo"},
        json=contact_payload(id="bad id"),
    )
    assert response.status_code == 422
