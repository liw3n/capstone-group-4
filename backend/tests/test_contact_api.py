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
        "id": "client-api-test",
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
    assert response.json()[0]["id"] == "client-api-test"
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


def test_contact_catalog_lists_by_request_fa_id(monkeypatch):
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
    assert executed[0][1] == ("adv-demo",)


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


def test_contact_replace_checks_body_and_path_ids(monkeypatch):
    monkeypatch.setattr(
        main,
        "replace_contact",
        lambda *_args: (_ for _ in ()).throw(AssertionError("storage must not be called")),
    )
    response = client.put(
        "/api/contacts/client-one",
        params={"fa_id": "adv-demo"},
        json=contact_payload(id="client-two"),
    )
    assert response.status_code == 400


def test_contact_replace_hides_inaccessible_records(monkeypatch):
    monkeypatch.setattr(main, "replace_contact", lambda *_args: None)
    response = client.put(
        "/api/contacts/client-api-test",
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
