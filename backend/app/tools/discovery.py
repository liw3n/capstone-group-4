"""Read-only synthetic campaign discovery for adviser review."""
from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.campaigns import repository
from app.campaigns.repository import CAMPAIGN_ID_PATTERN, CampaignStorageUnavailable, RequestScope

CampaignField = Literal[
    'campaign_id', 'name', 'start_date', 'end_date', 'age_groups', 'genders',
    'cash_bands', 'age_min', 'age_max', 'cash_min', 'cash_max', 'status',
]
CampaignId = Annotated[str, Field(pattern=CAMPAIGN_ID_PATTERN, max_length=69)]
CampaignName = Annotated[str, Field(min_length=1, max_length=255)]
DEFAULT_FIELDS = ['campaign_id', 'name', 'start_date', 'end_date', 'age_groups', 'genders', 'cash_bands']
DISCLAIMER = (
    'Synthetic campaign data for adviser review, not a product suitability '
    'assessment or financial advice. Outreach requires separate consent checks and confirmation.'
)


class ActiveCampaignArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    campaign_ids: list[CampaignId] | None = Field(default=None, max_length=100)
    campaign_names: list[CampaignName] | None = Field(default=None, max_length=100)
    limit: int = Field(default=1000, ge=1, le=1000, strict=True)
    fields: list[CampaignField] | None = Field(default=None, min_length=1, max_length=12)


def current_date() -> date:
    return datetime.now(ZoneInfo('Asia/Singapore')).date()


def markdown_table(columns: list[str], rows: list[dict]) -> str:
    def cell(value):
        if value is None:
            return 'Unknown'
        if isinstance(value, (tuple, list)):
            value = ', '.join(map(str, value)) or 'Any'
        return (str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                .replace('|', '&#124;').replace('\r', ' ').replace('\n', ' '))
    headers = [' '.join('ID' if word == 'id' else word.title() for word in column.split('_'))
               for column in columns]
    lines = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(columns)) + ' |']
    lines.extend('| ' + ' | '.join(cell(row[column]) for column in columns) + ' |' for row in rows)
    return '\n'.join(lines)


def execute_discovery(tool: str, arguments: dict, metadata: dict | None) -> dict:
    context = metadata.get('pulse_scope') if isinstance(metadata, dict) else None
    if not isinstance(context, dict):
        return {'data_source': 'synthetic', 'error_code': 'missing_context',
                'error': 'Adviser request context is required'}
    try:
        scope = RequestScope(fa_id=context.get('fa_id'), tenant_id=context.get('tenant_id'))
    except ValueError:
        return {'data_source': 'synthetic', 'error_code': 'missing_context',
                'error': 'Adviser request context is required'}
    if tool != 'get_active_campaigns':
        return {'data_source': 'synthetic', 'error': 'Unknown discovery tool'}
    try:
        query = ActiveCampaignArguments.model_validate(arguments)
    except ValidationError:
        return {'data_source': 'synthetic', 'error': 'Invalid tool arguments'}
    as_of = current_date()
    try:
        campaigns = repository.list_active_campaigns(scope, as_of, query.campaign_ids, query.campaign_names)
        rows = []
        fields = query.fields or DEFAULT_FIELDS
        # Keep the default order; always identify a campaign by its name.
        columns = list(dict.fromkeys(fields if 'name' in fields else ['name', *fields]))
        for campaign in campaigns:
            values = {'campaign_id': campaign.campaign_id, 'name': campaign.name,
                      'status': campaign.status, 'start_date': campaign.start_date.isoformat(),
                      'end_date': campaign.end_date.isoformat(), **vars(campaign.criteria)}
            rows.append({column: list(values[column]) if isinstance(values[column], tuple)
                         else values[column] for column in columns})
        returned = rows[:query.limit]
        result = {'data_source': 'synthetic', 'as_of_date': as_of.isoformat(), 'columns': columns,
                  'rows': returned, 'table': markdown_table(columns, returned),
                  'total_count': len(rows), 'returned_count': len(returned),
                  'truncated': len(rows) > query.limit, 'disclaimer': DISCLAIMER}
        return result
    except CampaignStorageUnavailable as exc:
        return {'data_source': 'synthetic', 'error_code': 'storage_unavailable', 'error': str(exc)}
