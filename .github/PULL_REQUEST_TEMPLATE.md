# Pull Request

## Type

- [ ] Editorial (spec clarification, typo fix — no version bump)
- [ ] Implementation change (reference server, client, conformance suite)
- [ ] Spec addition (new OPTIONAL field or well-known value — minor version bump)
- [ ] Spec breaking change (normative behavior change — major version bump + RFC process)

## Description

What does this PR do and why?

## Related issue

Closes # (if applicable)

## Checklist

### For all PRs
- [ ] CI passes (schema validation + reference server tests + conformance self-test)
- [ ] No LLM-specific or backend-specific requirements introduced
- [ ] CHANGELOG.md updated

### For spec changes
- [ ] `spec/SPEC.md` updated
- [ ] Relevant `spec/schemas/*.json` updated
- [ ] Relevant `spec/examples/*` updated and valid against schemas
- [ ] Reference server updated to implement the change
- [ ] Conformance test added or updated for the affected level
- [ ] RFC comment period satisfied (14 days for additions, 30 for breaking changes)
- [ ] Two maintainer sign-offs obtained (for additions) or all maintainers (for breaking changes)
