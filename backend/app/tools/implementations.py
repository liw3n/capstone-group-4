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


def get_client_follow_up_list(campaign_id: str) -> list[tuple[str, datetime]]:
    """
    Query the client follow-up list for a given campaign ID.
    """
    with _connection() as connection:
        # Engagement Status: 0 = Contacted, 1 = Engaged, 2 = Rejected
        rows = connection.execute(
            """
            SELECT client_id, last_engagement_date
            FROM mock_campaign_engagement
            WHERE campaign_id = %s and engagement_status = 0
            """,
            (campaign_id,),
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