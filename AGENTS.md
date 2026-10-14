# FRACXION — Engineering Rules

Temporary rules for the enterprise improvement work requested by the project owner.
Remove this file once the agreed work is complete; preserve existing nested instructions.

- Inspect the current architecture before changing code.
- Preserve multi-tenant isolation in every endpoint, query, task, and export.
- Never alter financial calculations without regression tests.
- Use Decimal for monetary calculations.
- Never bypass Django permissions or business services.
- Test concurrent database operations against PostgreSQL.
- Preserve existing migrations and data.
- Never expose credentials or environment secrets.
- Never deploy or push changes without authorization.
- Use version-compatible official documentation.
- Run relevant backend, frontend, and E2E tests.
- Review the Git diff and report failed or skipped checks.
- Do not claim success without verification.

## Enterprise work checkpoint

Complete architecture inspection, isolated baseline tests, `docs/ENTERPRISE_AUDIT.md`
and `docs/ENTERPRISE_ROADMAP.md` before starting enterprise feature development.
The owner must approve the roadmap before structural changes or new enterprise migrations.
Update the portfolio after the agreed implementation has been verified.
