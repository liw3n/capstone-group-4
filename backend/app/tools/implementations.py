from datetime import datetime

from ..store import _connection


def get_campaign_id(campaign: str) -> str:
    """
    Query the campaign ID based on the campaign name or ID.
    """
    if campaign.startswith("camp-"):
        return campaign

    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT campaign_id
            FROM mock_campaign
            WHERE name LIKE %s
            """,
            (f"%{campaign}%",),
        ).fetchall()

    if not rows:
        return campaign #
    if len(rows) > 1:
        raise ValueError(f"Multiple campaigns found with name: {campaign}")
    return rows[0]["campaign_id"]

def get_campaign_info(campaign_id: str) -> dict:
    """
    Query the campaign information based on the campaign ID.
    """
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT campaign_id, name, start_date, end_date, age_groups, genders, cash_bands
            FROM mock_campaign
            WHERE campaign_id = %s
            """,
            (campaign_id,),
        ).fetchone()

    if not row:
        raise ValueError(f"No campaign information found for campaign ID: {campaign_id}")

    return {
        "campaign_id": row["campaign_id"],
        "campaign_name": row["name"],
        "start_date": row["start_date"].isoformat() if row["start_date"] else None,
        "end_date": row["end_date"].isoformat() if row["end_date"] else None,
        "age_group": row["age_groups"],
        "genders": row["genders"],
        "cash_bands": row["cash_bands"]
    }


def get_client_follow_up_list(campaign_id: str, fa_id: str) -> list[tuple[str, datetime]]:
    """
    Return contacted clients with no recorded response for a campaign and adviser.
    """
    with _connection() as connection:
        # Status 0 means contacted with no recorded reply; 1 and 2 are responded outcomes.
        rows = connection.execute(
            """
            SELECT contact_id AS client_id, MAX(contacted_at) AS last_engagement_date
            FROM mock_campaign_contact_event
            WHERE campaign_id = %s and fa_id = %s and engagement_status = 0
            GROUP BY contact_id
            """,
            (campaign_id, fa_id),
        ).fetchall()

    if not rows:
        raise ValueError(f"No engagement information found for campaign ID: {campaign_id}")

    return [
        (row["client_id"], row["last_engagement_date"])
        for row in rows
    ]

def fetch_client_portfolio(client_id: str) -> dict:
    """
    Mock function to simulate fetching portfolio data for a client.
    In a real implementation, this would query the internal GWM API.
    """
    # Simulated portfolio data
    return {
        "client_id": client_id,
        "portfolio_value": 100000 + hash(client_id) % 50000,  # Randomized value for demonstration
        "risk_profile": "Moderate",
        "holdings": [
            {"asset": "Stock A", "quantity": 50},
            {"asset": "Bond B", "quantity": 30},
            {"asset": "ETF C", "quantity": 20},
        ],
    }

def fetch_client_profile(client_id: str) -> dict:
    """
    Mock function to simulate fetching profile data for a client.
    In a real implementation, this would query the internal GWM API.
    """
    # Simulated profile data
    return {
        "client_id": client_id,
        "name": f"Client {client_id[-4:]}",
        "age": 30 + hash(client_id) % 20,  # Randomized age for demonstration
        "email": f"{client_id[-4:]}@example.com",
    }