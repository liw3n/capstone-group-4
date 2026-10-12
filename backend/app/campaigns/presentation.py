"""Deterministic chat rendering for validated campaign draft artifacts."""

from app.campaigns.models import CampaignDraftArtifact


_AGE_GROUP_LABELS = {
    "under35": "Under 35",
    "35to44": "35–44",
    "45to54": "45–54",
    "55to64": "55–64",
    "65plus": "65 and above",
}
_GENDER_LABELS = {
    "female": "Female",
    "male": "Male",
}
_CASH_BAND_LABELS = {
    "under50k": "Below SGD 50,000",
    "50kTo250k": "SGD 50,000–250,000",
    "250kTo1m": "SGD 250,000–1 million",
    "above1m": "Above SGD 1 million",
}


def _labels(values: list[str], labels: dict[str, str], empty: str) -> str:
    return ", ".join(labels[value] for value in values) if values else empty


def _bullets(values: list[str], empty: str) -> str:
    return "\n".join(f"- {value}" for value in values) if values else f"- {empty}"


def _blockquote(value: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in value.splitlines())


def render_campaign_draft(artifact: CampaignDraftArtifact) -> str:
    """Render every validated field without asking the model to summarize it."""
    draft = artifact.draft
    criteria = draft.criteria
    citations = [
        f"`{citation.referenceId}` version {citation.version}"
        for citation in artifact.referencesUsed
    ]
    warnings = artifact.validation.warnings
    warning_summary = (
        "\n" + "\n".join(f"  - {warning}" for warning in warnings)
        if warnings
        else " None."
    )

    return "\n\n".join((
        "## Draft campaign",
        "**Draft only — not created. Adviser review is required.**",
        f"### Campaign name\n\n{draft.name}",
        f"### Objective\n\n{artifact.objective}",
        f"### Description\n\n{draft.description}",
        f"### Client message\n\n{_blockquote(draft.clientMessage)}",
        "### Target criteria\n\n"
        f"- **Age groups:** {_labels(criteria.ageGroups, _AGE_GROUP_LABELS, 'Any age')}\n"
        f"- **Genders:** {_labels(criteria.genders, _GENDER_LABELS, 'All genders')}\n"
        f"- **Cash bands:** {_labels(criteria.cashBands, _CASH_BAND_LABELS, 'No cash threshold')}",
        f"### Target demographic\n\n{draft.targetDemographicSummary}",
        "### Rationale\n\n"
        f"- **Age groups:** {draft.rationale['ageGroups']}\n"
        f"- **Genders:** {draft.rationale['genders']}\n"
        f"- **Cash bands:** {draft.rationale['cashBands']}",
        f"### Assumptions\n\n{_bullets(draft.assumptions, 'None stated.')}",
        f"### Disclaimer\n\n{draft.disclaimer}",
        f"### References used\n\n{_bullets(citations, 'No catalogue references cited.')}",
        "### Validation\n\n"
        "- **Schema:** Passed\n"
        "- **Policy:** Passed\n"
        f"- **Warnings:**{warning_summary}",
        "Review and edit this proposal before any later preview or confirmation step.",
    ))
