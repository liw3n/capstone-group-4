"""Inspect synthetic recommendations from PostgreSQL without Groq or MCP."""
import argparse
import json

from app.campaigns.matching import recommend_clients_for_campaign
from app.campaigns.repository import CampaignStorageUnavailable, DEMO_FA, RequestScope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign_id", help="Campaign ID, e.g. camp-1 or camp-2")
    parser.add_argument("--fa-id", default=DEMO_FA)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    try:
        result = recommend_clients_for_campaign(args.campaign_id, RequestScope(args.fa_id), args.limit)
    except (ValueError, CampaignStorageUnavailable) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
