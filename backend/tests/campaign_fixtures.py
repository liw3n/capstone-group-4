"""Offline test doubles only. Runtime data lives in PostgreSQL."""
from contextlib import contextmanager
from unittest.mock import patch

from app.campaigns.repository import Campaign, Client, Criteria, DEMO_FA

# IDs, names and criteria mirror the frontend seeds. Narrative in the campaign
# brief is NOT treated as extra suitability criteria.
CAMPAIGNS = (
    Campaign("camp-1", "Legacy Protection Refresh",
             Criteria(age_groups=("55to64", "65plus"), cash_bands=("250kTo1m", "above1m"))),
    Campaign("camp-2", "First Home Starter Bundle",
             Criteria(age_groups=("under35", "35to44"), cash_bands=("under50k", "50kTo250k"))),
)
CLIENTS = (
    Client("client-001", DEMO_FA, "Demo Client A", "1968-08-26", "female", 300_000),
    Client("client-002", DEMO_FA, "Demo Client B", "1956-08-26", "male", 1_000_000),
    Client("client-003", DEMO_FA, "Demo Client C", "1971-08-26", "female", 250_000),
    Client("client-004", DEMO_FA, "Demo Client D", "1971-08-27", "male", 300_000),
    Client("client-005", DEMO_FA, "Demo Client E", "1968-08-26", "male", 249_999),
    Client("client-006", DEMO_FA, "Demo Client F", "1996-08-26", "female", 49_999),
    Client("client-007", DEMO_FA, "Demo Client G", "1991-08-26", "male", 50_000),
    Client("client-008", DEMO_FA, "Demo Client H", "1982-08-26", "female", 249_999),
    Client("client-009", DEMO_FA, "Demo Client I", "1981-08-26", "male", 50_000),
    Client("client-010", DEMO_FA, "Demo Client J", None, "female", 300_000),
    Client("client-011", DEMO_FA, "Demo Client K", "1968-08-26", "male", None),
    Client("client-012", DEMO_FA, "Demo Client L", "1968-08-26", None, 300_000),
    Client("client-013", "adv-other-demo", "Other FA Demo Client", "1968-08-26", "male", 300_000),
    Client("client-014", DEMO_FA, "Other Tenant Demo Client", "1968-08-26", "female", 300_000,
           tenant_id="other-demo-tenant"),
)


@contextmanager
def fixture_repository():
    def load_campaign(campaign_id, scope):
        return next((campaign for campaign in CAMPAIGNS
                     if campaign.campaign_id == campaign_id
                     and campaign.tenant_id == scope.tenant_id
                     and scope.fa_id in campaign.fa_ids), None)

    def load_clients(scope):
        return tuple(client for client in CLIENTS
                     if client.tenant_id == scope.tenant_id and client.fa_id == scope.fa_id)

    with patch("app.campaigns.repository._load_campaign", side_effect=load_campaign), \
         patch("app.campaigns.repository._load_clients", side_effect=load_clients):
        yield
