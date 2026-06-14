# staging CMake conflict resolutions

This file records manual conflict resolutions made while inserting or replaying
the staging CMake sequence. Add an entry whenever `git am`, `git rebase`,
`git cherry-pick`, or an equivalent history rewrite stops for a conflict.

The goal is to make the branch repeatable and reviewable: a later maintainer
should be able to see which source commit or patch conflicted, which paths were
edited by hand, why the final state is correct for staging, and how it was
validated.

## Recording rule

For every manual resolution, record:

```text
### <short title>

- Operation: <git am / git rebase / git cherry-pick / manual amend>
- Applying: <patch filename or original commit hash and subject>
- Onto: <base commit hash and subject>
- Conflicting paths:
  - <path>
- Resolution:
  - <what was kept from the incoming gui-qml side>
  - <what was kept from the staging side>
  - <what was changed manually>
- Reason: <why this is the correct staging result>
- Validation:
  - <command and result>
```

When possible, collect the raw conflict context before resolving:

```bash
git status --short
git diff --name-only --diff-filter=U
git am --show-current-patch --stat 2>/dev/null || true
git rebase --show-current-patch --stat 2>/dev/null || true
```

Use `git rerere` only as a local accelerator. The rerere database is not the
audit record; this file is.

## Entries

No manual conflict resolutions are currently recorded for this patch series.
