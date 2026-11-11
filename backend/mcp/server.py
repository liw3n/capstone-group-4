import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from pydantic import Field

# Direct script execution puts backend/mcp on sys.path; add backend so the shared
# application tool implementations remain importable.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.tools.campaign_follow_up import (
    
    get_client_follow_up_list,
    fetch_client_portfolio,
    fetch_client_profile,
    get_campaign_info
)

from app.campaigns.clock import SINGAPORE
from app.campaigns.repository import (
    CAMPAIGN_ID_PATTERN,
    DEMO_TENANT,
    RequestScope,
    _is_uuid,
    _storage_tenant_id,
)
from app.campaigns.email import (
    ConfirmCampaignEmailArguments,
    DiscardCampaignEmailArguments,
    PrepareCampaignEmailArguments,
    confirm_campaign_email as execute_confirm_campaign_email,
    discard_campaign_email as execute_discard_campaign_email,
    prepare_campaign_email as execute_prepare_campaign_email,
)
from app.campaigns.models import (
    CampaignCategory,
    CampaignDraft,
    CampaignDraftChanges,
    CampaignDraftField,
    CampaignReferenceCitation,
)
from app.tools.campaign import execute_recommendation
from app.tools.campaign_draft import (
    execute_prepare_campaign_draft,
    execute_revise_campaign_draft,
)
from app.tools.campaign_references import execute_find_campaign_references
from app.tools.discovery import (
    CampaignFilters,
    CampaignField,
    CampaignId,
    CampaignName,
    execute_get_active_campaigns,
)
from app.tools.performance import execute_contact_performance, execute_contact_ranking
from app.tools.campaign_lookup import _words as _campaign_words, execute_resolve_campaign

# Initialize the FastMCP server instance
mcp = FastMCP(name="FastMCP Server")
logger = logging.getLogger(__name__)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False})
def recommend_clients_for_campaign(
    campaign_id: Annotated[str, Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)],
    ctx: Context,
    limit: Annotated[int, Field(ge=1, le=100, strict=True)] = 10,
) -> dict:
    """Find the pre-contact campaign audience: synthetic clients who meet the
    campaign's eligibility criteria, with reasons and missing-data gaps. Use
    this to find or filter potential clients before outreach. It does not identify
    clients already contacted or track replies; use campaign_follow_up for that.
    CRM records are read-only; large results create a temporary private snapshot.
    No ranking or product suitability assessment. Adviser and tenant
    scope come from API request metadata, never from model arguments.
    campaign_id must identify the requested campaign: use a known ID from current
    context or resolve the adviser's campaign name with resolve_campaign.
    Do not ask the adviser for an internal ID that the lookup tool can retrieve.
    Returns uncapped totals but at most 10 matching and 10 incomplete preview
    clients, even if a larger legacy limit is requested. Full results remain in
    an adviser-scoped backend snapshot referenced by list_id when truncated.
    Explain only these preview rows; do not invent further clients. The app
    appends the Excel download action separately, without another client table.
    """
    logger.info("MCP tool called: recommend_clients_for_campaign")
    request = ctx.request_context
    metadata = request.meta if request is not None else None
    if metadata is not None and not isinstance(metadata, dict):
        metadata = metadata.model_dump()
    return execute_recommendation(campaign_id, limit, metadata)

# campaign_follow_up sends the model profiles for at most this many of the
# longest-unengaged clients; total_unreplied_clients still counts all of them.
MAX_FOLLOW_UP_CANDIDATES = 15


def _follow_up_date(value: datetime | None) -> str | None:
    """Singapore calendar date of a member's last engagement, without the time."""
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(SINGAPORE)
    return value.date().isoformat()


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def campaign_follow_up(
    ctx: Context,
    campaign: Annotated[
        str | None,
        Field(
            max_length=200,
            description=(
                "The campaign name or ID explicitly mentioned by the user in the conversation "
                "(e.g., 'Q3 Wealth Campaign', 'Retirement Boost'). Always pass it when the "
                "adviser names a campaign, even in a campaign-scoped chat, so the server can "
                "check it against the open campaign. Omit it when the adviser names no "
                "campaign (e.g. 'this campaign')."
            ),
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(
            ge=1,
            le=25,
            strict=True,
            description="How many of the compared candidates to recommend for follow-up.",
        ),
    ] = 5,
) -> dict:
    """Find post-contact follow-ups: clients already contacted for this campaign
    who have no recorded reply/response, with their portfolio profiles. Use this
    only to find contacted clients awaiting a response, not to discover or filter
    a pre-contact eligible audience. For pre-contact criteria matching, use
    recommend_clients_for_campaign.

    When the chat is scoped to a campaign (the adviser opened it in the
    Campaigns workspace), that campaign is used. If the adviser also names a
    campaign, pass it: a name that identifies a different campaign returns a
    campaign_scope_mismatch error instead of results. Without a scope, pass the
    campaign name or ID the adviser mentioned.

    Returns profile and portfolio data for every unreplied client (oldest
    contact first) so they can all be compared; recommend the top `limit`.
    Do ranking and product suitability assessment based on the client's portfolio or profile to identify the most suitable clients for follow-up.
    Adviser and tenant scope come from API request metadata, never from model arguments.
    """
    try:
        logger.info("MCP tool called: campaign_follow_up")
        request = ctx.request_context
        metadata = request.meta if request is not None else None
        if metadata is not None and not isinstance(metadata, dict):
            metadata = metadata.model_dump()

        pulse_scope = metadata.get("pulse_scope") if isinstance(metadata, dict) else None
        fa_id = pulse_scope.get("fa_id") if isinstance(pulse_scope, dict) else None
        if not isinstance(fa_id, str) or not fa_id.strip():
            return {
                "error": "Adviser request context is required",
                "error_code": "missing_context",
            }
        raw_tenant_id = pulse_scope.get("tenant_id", DEMO_TENANT)
        if not isinstance(raw_tenant_id, str) or not raw_tenant_id.strip():
            return {"error": "Tenant request context is invalid", "error_code": "missing_context"}
        tenant_id = _storage_tenant_id(RequestScope(fa_id, raw_tenant_id))

        # 1. Resolve campaign source: a server-bound campaign scope takes precedence,
        # otherwise resolve the campaign named by the adviser.
        selected_campaign_id = metadata.get("campaign_id") if isinstance(metadata, dict) else None
        campaign_query = campaign.strip() if isinstance(campaign, str) else ""
        campaign_info = None
        if selected_campaign_id is not None:
            if (
                not isinstance(selected_campaign_id, str)
                or re.fullmatch(CAMPAIGN_ID_PATTERN, selected_campaign_id) is None
            ):
                return {
                    "error": "Selected campaign context is invalid",
                    "error_code": "invalid_campaign_context",
                }
            campaign_id = selected_campaign_id
            if campaign_query:
                # A campaign named in the prompt must be the scoped campaign;
                # never silently answer for a different campaign.
                try:
                    campaign_info = get_campaign_info(campaign_id, fa_id, tenant_id)
                except ValueError as error:
                    return {
                        "error": f"{error}. Ask the adviser to reopen the campaign.",
                        "error_code": "campaign_unavailable",
                    }
                mismatch = _follow_up_scope_mismatch(
                    campaign_query, campaign_id, campaign_info.get("campaign_name"), metadata
                )
                if mismatch is not None:
                    return mismatch
        else:
            if not campaign_query:
                return {
                    "error": (
                        "Campaign name or ID is missing. Extract the campaign name from the "
                        "adviser's message and pass it as 'campaign'; if none was mentioned, "
                        "ask the adviser which campaign they mean."
                    ),
                    "error_code": "missing_campaign",
                }
            if _is_uuid(campaign_query):
                campaign_id = campaign_query
            else:
                # Share resolve_campaign's adviser-scoped name matching 
                resolution = execute_resolve_campaign({"campaign_name": campaign_query}, metadata)
                if "error_code" in resolution:
                    return {"error": resolution["error"], "error_code": resolution["error_code"]}
                if resolution["status"] == "ambiguous":
                    return {
                        "error": (
                            "Several campaigns match that name. Ask the adviser which "
                            "campaign they mean."
                        ),
                        "error_code": "campaign_unavailable",
                        "campaign_candidates": resolution["candidates"],
                    }
                if resolution["status"] != "matched":
                    return {"error": resolution["message"], "error_code": "campaign_unavailable"}
                campaign_id = resolution["campaign_id"]

        if campaign_info is None:
            try:
                campaign_info = get_campaign_info(campaign_id, fa_id, tenant_id)
            except ValueError as error:
                return {
                    "error": f"{error}. Ask the adviser to confirm the exact campaign name.",
                    "error_code": "campaign_unavailable",
                }
        client_info = get_client_follow_up_list(campaign_id, fa_id, tenant_id)

        # 2. Fetch profile and portfolio context for the MAX_FOLLOW_UP_CANDIDATES
        # longest-unengaged candidates (never-engaged first, then earliest
        # engagement date).
        client_info = sorted(
            client_info,
            key=lambda row: (row[1] is not None, row[1] or datetime.min),
        )
        client_profiles = []
        for client_id, last_engagement_date in client_info[:MAX_FOLLOW_UP_CANDIDATES]:
            portfolio = fetch_client_portfolio(client_id)
            profile = fetch_client_profile(client_id, fa_id, tenant_id)
            # Every candidate is resent to the model, so drop the repeated
            # client IDs and the email address, which ranking does not use.
            client_profiles.append({
                "client_id": client_id,
                "portfolio_data": {key: value for key, value in portfolio.items()
                                   if key != "client_id"},
                "profile_data": {key: value for key, value in profile.items()
                                 if key not in {"client_id", "email"}},
                "last_engagement_date": _follow_up_date(last_engagement_date),
            })
        recommend_count = min(limit, len(client_profiles))

        additional_instructions = (
            "These candidates have already been contacted and have no recorded reply; "
            "they are not a pre-contact eligible audience. Do not add other clients or "
            "claim a reply status not present in the results. "
            f"Compare all {len(client_profiles)} candidates and recommend the top "
            f"{recommend_count} for follow-up, ranked. "
            "Dynamically formulate and explain a tailored follow-up justification for each "
            "recommended candidate by evaluating their specific portfolio data, profile "
            "attributes, and the elapsed time since their last engagement date against the "
            "campaign's eligibility criteria. "
            "Do not infer suitability or priority from any other context. "
            "This tool does not check outreach consent or authorise another communication; "
            "adviser confirmation and separate channel consent checks are required before outreach."
        )

        # 3. Return the rich data back to the LLM
        return {
            "campaign_info": campaign_info,
            "total_unreplied_clients": len(client_info),
            "requested_limit": limit,
            "compared_candidates": len(client_profiles),
            "candidates": client_profiles,
            "additional_instructions": additional_instructions,
        }

    except Exception as e:
        return {
            "error": str(e),
            "error_code": "failed_tool_call"
        }


def _campaign_name_key(value: str) -> str:
    """Normalise a campaign name the way resolve_campaign compares names."""
    words = _campaign_words(value).split()
    if words and words[0] == "the":
        words = words[1:]
    if words and words[-1] == "campaign":
        words = words[:-1]
    return " ".join(words)


def _follow_up_scope_mismatch(
    campaign_query: str, scoped_id: str, scoped_name: str | None, metadata: dict
) -> dict | None:
    """Return an error when the named campaign is not the scoped campaign."""
    if _is_uuid(campaign_query):
        if campaign_query.lower() == scoped_id.lower():
            return None
    elif scoped_name and _campaign_name_key(campaign_query) == _campaign_name_key(scoped_name):
        return None
    else:
        resolution = execute_resolve_campaign({"campaign_name": campaign_query}, metadata)
        if "error_code" in resolution:
            return {"error": resolution["error"], "error_code": resolution["error_code"]}
        if resolution["status"] == "matched" and str(resolution["campaign_id"]).lower() == scoped_id.lower():
            return None
        if resolution["status"] == "ambiguous" and any(
            str(item["campaign_id"]).lower() == scoped_id.lower()
            for item in resolution["candidates"]
        ):
            return None

    open_name = scoped_name or "the selected campaign"
    return {
        "error": (
            f"The adviser has the '{open_name}' campaign open but asked about "
            f"'{campaign_query}'. No follow-up results were returned. Tell the adviser "
            "the campaign they named differs from the open campaign, and ask them to open "
            "that campaign or ask from the general chat. If they did not name a different "
            "campaign, call again without the campaign argument."
        ),
        "error_code": "campaign_scope_mismatch",
        "scoped_campaign": open_name,
        "requested_campaign": campaign_query,
    }


def _request_metadata(ctx: Context) -> dict | None:
    request = ctx.request_context
    metadata = request.meta if request is not None else None
    return metadata if metadata is None or isinstance(metadata, dict) else metadata.model_dump()


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False})
def prepare_campaign_email(
    ctx: Context,
    campaign_id: Annotated[str | None, Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)] = None,
    recipient_ids: Annotated[list[str] | None, Field(min_length=1, max_length=100)] = None,
    subject: Annotated[str | None, Field(min_length=1, max_length=200)] = None,
    body: Annotated[str | None, Field(min_length=1, max_length=10_000)] = None,
    signoff_name: Annotated[str | None, Field(min_length=2, max_length=100)] = None,
) -> dict:
    """Prepare an expiring campaign-email preview for adviser review.

    The subject and body are AI-generated drafts. The server resolves the
    selected campaign, recalculates criteria matches, enforces adviser/tenant
    ownership and email consent, and stores the exact preview. This tool never
    sends email. Omit recipient_ids to use all consenting campaign matches.
    """
    logger.info("MCP tool called: prepare_campaign_email")
    arguments = PrepareCampaignEmailArguments(
        campaign_id=campaign_id,
        recipient_ids=recipient_ids,
        subject=subject,
        body=body,
        signoff_name=signoff_name,
    )
    return execute_prepare_campaign_email(arguments, _request_metadata(ctx))


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
def confirm_campaign_email(ctx: Context) -> dict:
    """Send the latest reviewed campaign email after exact adviser confirmation.

    The confirmation phrase is read from trusted latest-message metadata, never
    from model arguments. The server rechecks campaign access, criteria and
    email consent, records provider outcomes, and appends successful contacts to
    campaign history. Repeated confirmation is idempotent.
    """
    logger.info("MCP tool called: confirm_campaign_email")
    ConfirmCampaignEmailArguments()
    return execute_confirm_campaign_email(_request_metadata(ctx))


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
def discard_campaign_email(ctx: Context) -> dict:
    """Discard the latest unsent campaign-email preview in this chat session.

    Adviser and tenant scope come from trusted request metadata. Sent or
    in-progress batches are never modified, and this operation never sends an
    email.
    """
    logger.info("MCP tool called: discard_campaign_email")
    DiscardCampaignEmailArguments()
    return execute_discard_campaign_email(_request_metadata(ctx))


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def find_campaign_references(
    objective: Annotated[
        str,
        Field(
            min_length=10,
            max_length=2_000,
            description="The adviser's plain-language campaign business objective.",
        ),
    ],
    ctx: Context,
    categories: Annotated[
        list[CampaignCategory] | None,
        Field(max_length=5, description="Optional campaign categories explicitly requested."),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=3, strict=True)] = 3,
) -> dict:
    """Find up to three approved synthetic patterns for campaign drafting.

    Read-only: it does not inspect clients, assess suitability, create a draft,
    create a campaign or mutate CRM data. Adviser and tenant scope come only
    from trusted API metadata, never model arguments.
    """
    logger.info("MCP tool called: find_campaign_references")
    return execute_find_campaign_references(
        {"objective": objective, "categories": categories, "limit": limit},
        _request_metadata(ctx),
    )


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def prepare_campaign_draft(
    objective: Annotated[
        str,
        Field(
            min_length=10,
            max_length=2_000,
            description="The same campaign objective used to retrieve references.",
        ),
    ],
    retrievalToken: Annotated[str, Field(min_length=20, max_length=8_000)],
    referencesUsed: Annotated[list[CampaignReferenceCitation], Field(max_length=3)],
    draft: CampaignDraft,
    ctx: Context,
) -> dict:
    """Validate and package one AI-generated campaign draft for adviser review.

    Requires a valid reference-retrieval token and accepts citations only from
    that retrieval result. Read-only: it does not persist, create, activate or
    send a campaign and always returns created=false on success.
    """
    logger.info("MCP tool called: prepare_campaign_draft")
    return execute_prepare_campaign_draft(
        {
            "objective": objective,
            "retrievalToken": retrievalToken,
            "referencesUsed": [item.model_dump() for item in referencesUsed],
            "draft": draft.model_dump(),
        },
        _request_metadata(ctx),
    )


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def revise_campaign_draft(
    objective: Annotated[
        str,
        Field(
            min_length=10,
            max_length=2_000,
            description="The original validated campaign business objective.",
        ),
    ],
    referencesUsed: Annotated[list[CampaignReferenceCitation], Field(max_length=3)],
    currentDraft: CampaignDraft,
    proposedChanges: CampaignDraftChanges,
    fields: Annotated[list[CampaignDraftField], Field(min_length=1, max_length=7)],
    revision: Annotated[int, Field(ge=1, strict=True)],
    ctx: Context,
    instruction: Annotated[str | None, Field(max_length=2_000)] = None,
) -> dict:
    """Validate a selective revision of an existing campaign draft.

    Read-only: only fields explicitly listed in fields may change. Every other
    field is restored from currentDraft, the complete policy is rerun, and the
    result remains an uncreated adviser-review artifact. The calling host must
    supply the authoritative previously validated draft and revision.
    """
    logger.info("MCP tool called: revise_campaign_draft")
    return execute_revise_campaign_draft(
        {
            "objective": objective,
            "referencesUsed": [item.model_dump() for item in referencesUsed],
            "currentDraft": currentDraft.model_dump(),
            "proposedChanges": proposedChanges.model_dump(exclude_unset=True),
            "fields": fields,
            "instruction": instruction,
            "revision": revision,
        },
        _request_metadata(ctx),
    )


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def get_active_campaigns(
    ctx: Context,
    campaign_ids: Annotated[list[CampaignId] | None, Field(max_length=100)] = None,
    campaign_names: Annotated[list[CampaignName] | None, Field(max_length=100)] = None,
    fields: Annotated[list[CampaignField] | None, Field(min_length=1, max_length=13)] = None,
    limit: Annotated[int, Field(ge=1, le=1000, strict=True)] = 1000,
    filters: CampaignFilters | None = None,
) -> dict:
    """List accessible campaigns with status exactly 'active' as a table.

    Optional exact IDs/names restrict campaigns (both filters intersect).
    Omit fields unless the user explicitly requests particular details. Defaults:
    name, description, start_date, end_date, age_groups, genders, cash_bands.
    Campaigns come from GET /api/campaigns, scoped to the tenant and creator.
    Name is always included; campaign_id is an allowed output field.
    Additional restrictions belong in filters, independently of output fields.
    Audience filters find overlapping eligibility, combining age/gender/cash
    with AND. Preset bands and custom ranges are OR within each dimension.
    Dates do not determine active status. Report today's Singapore date.
    Active is a filter, not a request to show only status. User identity (fa_id)
    comes only from API metadata. Report empty results and truncation.
    """
    logger.info("MCP tool called: get_active_campaigns")
    return execute_get_active_campaigns(
        {
            "campaign_ids": campaign_ids,
            "campaign_names": campaign_names,
            "fields": fields,
            "limit": limit,
            "filters": filters.model_dump(mode="json") if filters is not None else None,
        },
        _request_metadata(ctx),
    )


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def resolve_campaign(
    campaign_name: Annotated[str, Field(min_length=1, max_length=255)],
    ctx: Context,
) -> dict:
    """Resolve a campaign name to its ID for another campaign tool.

    Use when the adviser names a campaign and you need its campaign_id, for
    example before recommend_clients_for_campaign. Accepts case/punctuation
    variations, a conversational "campaign" suffix and whole-word partial names.
    Returns matched with an ID/name, ambiguous with a small candidate list, or
    not_found. On matched, continue the original request using the returned ID.
    On ambiguous, ask which campaign name the adviser means; never guess an ID.
    Read-only; searches only accessible active campaigns, with adviser/tenant
    scope from request metadata. Does not retrieve or recommend clients.
    For a campaign catalogue/table, use get_active_campaigns instead.
    """
    logger.info("MCP tool called: resolve_campaign")
    return execute_resolve_campaign({"campaign_name": campaign_name}, _request_metadata(ctx))


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def get_campaign_contact_performance(
    ctx: Context,
    campaign: Annotated[
        str | None,
        Field(description="Exact campaign name or ID from the current message; omit when one is selected.",
              min_length=1, max_length=255),
    ] = None,
    period: Annotated[
        Literal["this_week", "last_week", "specific_week"],
        Field(description="Choose which week's member additions to show. specific_week needs week_of; this is not a weekly contact count."),
    ] = "this_week",
    week_of: Annotated[
        str | None,
        Field(description="Required for specific_week: a date within the requested week as YYYY-MM-DD. Omit otherwise.",
              min_length=10, max_length=10, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    ] = None,
) -> dict:
    """Review one accessible campaign using membership and recorded email totals.

    Returns cumulative member/email figures and members added this, last, or a
    named Monday-Sunday week in Singapore time. Exact weekly contact or email
    counts are unavailable without an event history. Never describe members
    added as clients contacted.
    Adviser and tenant scope come from API metadata, never model arguments.
    """
    logger.info("MCP tool called: get_campaign_contact_performance")
    return execute_contact_performance({"campaign": campaign, "period": period,
                                        "week_of": week_of},
                                       _request_metadata(ctx))


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
def get_campaign_contact_ranking(
    ctx: Context,
    period: Annotated[
        Literal["campaign_to_date", "this_week", "last_week"],
        Field(description="Period for members_added. Email reach and coverage support campaign_to_date only."),
    ] = "campaign_to_date",
    metric: Annotated[
        Literal["clients_emailed", "members_added", "email_coverage"],
        Field(description="Rank cumulative clients with a recorded email, members added, or the percentage of members with a recorded email. Never treat these as all clients contacted."),
    ] = "clients_emailed",
    direction: Annotated[
        Literal["most", "least"],
        Field(description="Use least only with email_coverage; defaults to most."),
    ] = "most",
) -> dict:
    """Rank accessible campaigns by recorded email reach, coverage, or member additions.

    Compare all campaigns available to this adviser, regardless of the selected
    campaign. Coverage excludes campaigns with no members and includes ties.
    Weekly email reach and general contact counts are unavailable.
    """
    logger.info("MCP tool called: get_campaign_contact_ranking")
    return execute_contact_ranking({"period": period, "metric": metric,
                                    "direction": direction},
                                   _request_metadata(ctx))


# 3. Run the Server
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from app.config import get_settings
    mcp.run(transport="http", host="127.0.0.1" if get_settings().pulse_hosted_demo else "0.0.0.0", port=8001)
