from datetime import datetime

from ..store import _connection


def get_campaign_id(campaign: str, fa_id: str, tenant_id: str | None = None) -> str:
    """
    Query the campaign ID based on the campaign name or ID.
    """
    if campaign.startswith("camp-"):
        return campaign

    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT campaign_id
            FROM campaign
            WHERE LOWER(name) LIKE LOWER(%s) AND tenant_id = %s
              AND created_by_user_id = %s AND is_deleted = FALSE
            """,
            (f"%{campaign}%", tenant_id or fa_id, fa_id),
        ).fetchall()

    if not rows:
        return campaign #
    if len(rows) > 1:
        raise ValueError(f"Multiple campaigns found with name: {campaign}")
    return rows[0]["campaign_id"]

def get_campaign_info(campaign_id: str, fa_id: str, tenant_id: str | None = None) -> dict:
    """
    Query the campaign information based on the campaign ID.
    """
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT campaign_id, name, start_date, end_date, audience_criteria
            FROM campaign
            WHERE campaign_id = %s AND tenant_id = %s
              AND created_by_user_id = %s AND is_deleted = FALSE
            """,
            (campaign_id, tenant_id or fa_id, fa_id),
        ).fetchone()

    if not row:
        raise ValueError(f"No campaign information found for campaign ID: {campaign_id}")

    return {
        "campaign_id": row["campaign_id"],
        "campaign_name": row["name"],
        "start_date": row["start_date"].isoformat() if row["start_date"] else None,
        "end_date": row["end_date"].isoformat() if row["end_date"] else None,
        "campaign_criteria": row["audience_criteria"]
    }


def get_client_follow_up_list(
    campaign_id: str, fa_id: str, tenant_id: str | None = None
) -> list[tuple[str, datetime]]:
    """
    Query the client follow-up list for a given campaign ID and FA ID.
    Returns clients whose max engagement status is 0 (contacted but not engaged/rejected),
    along with their last contacted date.
    """
    with _connection() as connection:
        # Get clients that have been contacted (max status = 0) and their last contacted date
        contacts = connection.execute(
            """
            SELECT m.contact_id AS client_id,
                   MAX(coalesce(m.emailed_at, m.added_at)) AS last_engagement_date
            FROM campaign_member AS m
            JOIN campaign AS campaign
              ON campaign.tenant_id = m.tenant_id
             AND campaign.campaign_id = m.campaign_id
            JOIN contact AS client
              ON client.tenant_id = m.tenant_id
             AND client.contact_id = m.contact_id
            WHERE m.campaign_id = %s AND m.tenant_id = %s
              AND m.is_deleted = FALSE
              AND campaign.created_by_user_id = %s
              AND campaign.is_deleted = FALSE
              AND m.added_by_user_id = %s
              AND client.is_deleted = FALSE
              AND (client.assigned_to_user_id = %s OR
                   (client.assigned_to_user_id IS NULL
                    AND client.created_by_user_id = %s))
            GROUP BY m.contact_id
            HAVING MAX(m.engagement_status) = 0;
            """,
            (campaign_id, tenant_id or fa_id, fa_id, fa_id, fa_id, fa_id),
        ).fetchall()

    if not contacts:
        raise ValueError(f"No unreplied clients found for campaign ID: {campaign_id}")

    return [(row["client_id"], row["last_engagement_date"]) for row in contacts]

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

def fetch_client_profile(client_id: str, fa_id: str, tenant_id: str | None = None) -> dict:
    """
    Mock function to simulate fetching profile data for a client.
    In a real implementation, this would query the internal GWM API.
    """
    with _connection() as connection:
        row = connection.execute(
            """
            SELECT full_name, date_of_birth, email
            FROM contact
            WHERE contact_id = %s AND tenant_id = %s AND is_deleted = FALSE
              AND (assigned_to_user_id = %s OR
                   (assigned_to_user_id IS NULL AND created_by_user_id = %s))
            """,
            (client_id, tenant_id or fa_id, fa_id, fa_id),
        ).fetchone()

    if row:
        age = (datetime.now().date() - row["date_of_birth"]).days // 365 if row["date_of_birth"] else None
        return {
            "client_id": client_id,
            "name": row["full_name"],
            "age": age,
            "email": row["email"],
        }
    else:
        return {
            "client_id": client_id,
            "name": f"Client {client_id[-4:]}",
            "age": None,
            "email": None,
        }
