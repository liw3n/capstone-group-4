"""Runtime campaign dates must follow Singapore, not the old seed date."""
from dataclasses import replace
from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest

from app.campaigns import clock, matching, repository
from app.campaigns.repository import Campaign, CampaignInactive, Client, Criteria, RequestScope
from app.tools import discovery


@pytest.mark.parametrize("instant, expected", [
    ("2026-11-06T15:59:59+00:00", date(2026, 11, 6)),
    ("2026-11-06T16:00:00+00:00", date(2026, 11, 7)),
])
def test_shared_clock_uses_singapore_midnight(monkeypatch, instant, expected):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(instant).astimezone(tz or timezone.utc)

    monkeypatch.setattr(clock, "datetime", FrozenDatetime)
    assert clock.current_date() == expected
    assert discovery.current_date() == expected


@pytest.mark.parametrize("as_of, active", [
    (date(2026, 8, 31), False),
    (date(2026, 9, 1), True),
    (date(2026, 11, 7), True),
    (date(2026, 12, 31), True),
    (date(2027, 1, 1), False),
])
def test_activity_uses_current_date_and_inclusive_schedule(monkeypatch, as_of, active):
    monkeypatch.setattr(clock, "current_date", lambda: as_of)
    campaign = Campaign("campaign", "September campaign", Criteria(),
                        start_date=date(2026, 9, 1), end_date=date(2026, 12, 31))
    if active:
        repository.require_active(campaign)
    else:
        with pytest.raises(CampaignInactive, match=as_of.isoformat()):
            repository.require_active(campaign)


@pytest.mark.parametrize("changes", [
    {"status": "draft"}, {"status": "inactive"},
    {"start_date": None}, {"end_date": None},
    {"start_date": date(2026, 11, 8)}, {"end_date": date(2026, 11, 6)},
])
def test_invalid_or_noncurrent_campaigns_stop_before_loading_clients(monkeypatch, changes):
    monkeypatch.setattr(clock, "current_date", lambda: date(2026, 11, 7))
    campaign = Campaign("campaign", "Campaign", Criteria())
    monkeypatch.setattr(matching, "get_campaign", lambda *_: replace(campaign, **changes))
    read_clients = Mock()
    monkeypatch.setattr(matching, "list_clients_for_fa", read_clients)
    with pytest.raises(CampaignInactive, match="2026-11-07"):
        matching.recommend_clients_for_campaign("campaign", RequestScope("adviser"))
    read_clients.assert_not_called()


def test_recommendation_uses_one_current_date_for_activity_age_and_result(monkeypatch):
    # A midnight rollover during a request must not split its activity/age dates.
    today = Mock(side_effect=[date(2026, 11, 7), date(2026, 11, 8)])
    monkeypatch.setattr(clock, "current_date", today)
    campaign = Campaign("campaign", "Early Career Wealth Foundations",
                        Criteria(age_groups=("under35",)),
                        start_date=date(2026, 9, 1), end_date=date(2026, 11, 7))
    monkeypatch.setattr(matching, "get_campaign", lambda *_: campaign)
    monkeypatch.setattr(matching, "list_clients_for_fa", lambda *_: (
        Client("birthday", "adviser", "Birthday Client", "1991-11-07", "Female", 10000),
        Client("tomorrow", "adviser", "Tomorrow Client", "1991-11-08", "Female", 10000),
    ))
    result = matching.recommend_clients_for_campaign("campaign", RequestScope("adviser"))
    assert result["as_of_date"] == "2026-11-07"
    assert [client["contact_id"] for client in result["clients"]] == ["tomorrow"]
    assert result["excluded_count"] == 1
    assert "Age 34" in result["clients"][0]["reasons"][0]
    today.assert_called_once_with()


def test_standalone_age_helpers_use_the_current_singapore_date(monkeypatch):
    monkeypatch.setattr(clock, "current_date", lambda: date(2026, 11, 7))
    assert matching.age_from_dob("1991-11-07") == 35
    assert matching.age_from_dob("1991-11-08") == 34
    assert matching.age_from_dob("2026-11-08") is None
    assert matching.age_from_dob("1971-08-27", date(2026, 8, 26)) == 54
