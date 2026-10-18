# Campaign generation test cases

These five synthetic campaign drafts are reference outputs for testing a future
MCP campaign-generation tool. Each case begins with a financial adviser's
plain-language objective and provides the six fields expected in a complete,
ready-to-review proposal. The adviser must be able to edit or regenerate every
field before explicitly approving creation; generating a draft must not create,
publish, or send the campaign.

The targeting values deliberately use the prototype's existing campaign schema:

- `ageGroups`: `under35`, `35to44`, `45to54`, `55to64`, `65plus`
- `genders`: `male`, `female`; an empty list means no gender restriction
- `cashBands`: `under50k`, `50kTo250k`, `250kTo1m`, `above1m`

Wording need not match these examples verbatim. Tests should assess whether a
generated draft is complete, internally consistent with the objective, valid
against the schema, educational rather than prescriptive, and clearly subject to
adviser review.

## Retirement asset consolidation review

**Plain-language objective**

> I want to run a campaign encouraging clients nearing retirement to consolidate
> their assets with us.

**Campaign name:** Retirement Asset Consolidation Review

**Campaign description:** Invite clients nearing or already in retirement to an
educational review of savings, investments, and retirement accounts held across
multiple institutions. The conversation should help clients understand their
overall position, identify administrative complexity, and consider the potential
benefits and trade-offs of consolidation without assuming that moving every asset
is suitable.

**Client messaging:** As retirement approaches, accounts accumulated over the
years can become difficult to track as one complete plan. We are offering a
complimentary retirement asset review to help you map what you hold, understand
fees and access considerations, and discuss whether simplifying selected holdings
could support your goals. Any recommendation would depend on your circumstances
and a separate suitability assessment; this invitation is educational and is not
financial advice.

**Target age group:** Ages 55 and above.
`ageGroups: ["55to64", "65plus"]`

**Target demographic:** All genders; clients approaching or already in
retirement who may hold assets across multiple institutions.
`genders: []`

**Target cash availability:** SGD 250,000 and above.
`cashBands: ["250kTo1m", "above1m"]`

## Cross-turn revision routing cases

These cases run only after a scoped active draft exists. Every successful edit
must retain the draft ID, advance the revision exactly once, return a structured
`campaignDraft`, preserve independent unselected fields and avoid campaign-table
writes.

| Adviser message | Expected action |
| --- | --- |
| `The target age should be above 65 years old and cash availability should be more than 250k` | Revise `ageGroups` and `cashBands`; server locks them to `65plus` and `250kTo1m` + `above1m`. Refresh description, client message, demographic summary and rationale without changing the name. Surface warnings that the strict thresholds were approximated by inclusive fixed bands. |
| `Age 65+, cash 250k and above` | Use the strict active-draft classifier, then perform the same structured revision. Never return a prose-only proposal. |
| `Actually remove the cash restriction` | Set `cashBands` to an empty list and refresh dependent targeting text. |
| `Show clients above 65 with more than 250k cash` | Preserve client-matching tool intent; do not revise or load the active draft. |
| `How did this campaign perform last week?` | Preserve performance-tool intent; do not revise the active draft. |
| `Draft an email for this campaign` | Preserve email preview/confirmation routing; do not revise the active draft. |

For concurrent review, submit revision `n` after revision `n + 1` already exists.
The stale request must return `409`, must not write, and the frontend must reload
the latest scoped revision before allowing another edit.

## Young family protection check-in

**Plain-language objective**

> I want younger clients who are starting families to review whether their
> protection still matches their new responsibilities.

**Campaign name:** Growing Family Protection Check-in

**Campaign description:** Offer younger clients and new parents an educational
review of how marriage, children, housing commitments, and changing household
income can affect protection needs. The campaign should focus on understanding
gaps and priorities rather than promoting a specific product.

**Client messaging:** A growing family can change what financial security means.
We are offering a complimentary protection check-in to help you review household
commitments, existing cover, and the areas you may want to discuss further. The
session is educational, with no obligation to make changes. Any recommendation
would require a separate assessment of your needs and circumstances and should
not be treated as financial advice from this message alone.

**Target age group:** Below age 45.
`ageGroups: ["under35", "35to44"]`

**Target demographic:** All genders; younger clients with new or growing family
responsibilities.
`genders: []`

**Target cash availability:** Below SGD 250,000.
`cashBands: ["under50k", "50kTo250k"]`

## Education funding readiness review

**Plain-language objective**

> I want to help mid-career parents assess whether they are on track for their
> children's future education costs.

**Campaign name:** Education Funding Readiness Review

**Campaign description:** Engage mid-career clients in a structured review of
their education-funding goals, expected time horizon, current savings, and the
effect of competing priorities such as housing and retirement. The campaign
should help clients identify planning questions and possible shortfalls without
presenting projected outcomes as guaranteed.

**Client messaging:** Education costs can arrive alongside other major goals, so
it helps to review the plan before the funding date gets close. We are offering a
complimentary session to map your target, time horizon, current savings, and the
trade-offs with your other priorities. This is an educational planning review,
not a guarantee of future returns or personalised financial advice; any next step
requires a separate suitability assessment.

**Target age group:** Ages 35 to 54.
`ageGroups: ["35to44", "45to54"]`

**Target demographic:** All genders; mid-career clients planning for children's
education while balancing other financial goals.
`genders: []`

**Target cash availability:** SGD 50,000 to below SGD 1 million.
`cashBands: ["50kTo250k", "250kTo1m"]`

## Women's retirement confidence review

**Plain-language objective**

> I want to invite women in the later stages of their careers to review their
> retirement readiness and any gaps caused by career breaks or caregiving.

**Campaign name:** Women's Retirement Confidence Review

**Campaign description:** Provide women approaching retirement with an
educational review that considers savings, expected retirement income, career or
caregiving breaks, and desired lifestyle. The campaign should encourage informed
planning without generalising individual needs or recommending a product based
on gender alone.

**Client messaging:** Career and caregiving paths can affect retirement planning
in different ways. We are offering a complimentary retirement confidence review
to help you take stock of your savings, expected income, and the questions that
matter for your preferred lifestyle. The discussion is educational and tailored
recommendations, if any, would follow only after a separate assessment of your
individual circumstances. This invitation is not financial advice.

**Target age group:** Ages 45 to 64.
`ageGroups: ["45to54", "55to64"]`

**Target demographic:** Women in the later stages of their careers who may want
to review the effect of career or caregiving breaks on retirement readiness.
`genders: ["female"]`

**Target cash availability:** SGD 50,000 to below SGD 1 million.
`cashBands: ["50kTo250k", "250kTo1m"]`

## Legacy and estate conversation

**Plain-language objective**

> I want clients with substantial liquid assets to start a conversation about
> how they want their wealth managed and transferred to the next generation.

**Campaign name:** Legacy and Estate Planning Conversation

**Campaign description:** Invite established clients with substantial liquid
assets to an educational conversation about legacy objectives, beneficiary
intentions, existing arrangements, liquidity needs, and questions that may need
legal or tax input. The campaign must not imply that a financial adviser replaces
qualified legal or tax professionals.

**Client messaging:** A clear legacy plan starts with understanding what you want
your wealth to achieve and whether your current arrangements still reflect those
intentions. We are offering a complimentary conversation to help you organise the
key questions around beneficiaries, liquidity, and wealth transfer. This is an
educational review, not legal, tax, or financial advice; any recommendation would
require a separate suitability assessment and specialist input where appropriate.

**Target age group:** Ages 55 and above.
`ageGroups: ["55to64", "65plus"]`

**Target demographic:** All genders; established clients beginning or revisiting
legacy and intergenerational wealth planning.
`genders: []`

**Target cash availability:** SGD 250,000 and above.
`cashBands: ["250kTo1m", "above1m"]`
