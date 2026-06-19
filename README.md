# gui-qml maintainer tools

## `port_qml_commits.py`

Ports reviewed commits from `gui-qml-main` into a staging Bitcoin Core checkout,
rewriting QML paths into `src/qml` and adding provenance trailers to each
generated commit.

Typical use from the target checkout:

```bash
cd ../gui-qml-staging
../gui-qml-maintainer-tools/port_qml_commits.py --source ../gui-qml-main bitcoin-core/gui-qml#450
```

You can dry-run first:

```bash
../gui-qml-maintainer-tools/port_qml_commits.py --source ../gui-qml-main --dry-run bitcoin-core/gui-qml#450
```

Selectors can be full PR ids, short PR numbers, individual commits, or
two-dot ranges. PR selectors are resolved from the source first-parent history,
then the reviewed side commits are replayed oldest-first.

Generated commits include trailers like:

```text
Rebased-From: <source commit>
Github-Pull: bitcoin-core/gui-qml#450
```

The default path maps are `src/qml:src/qml` and `qml:src/qml`, so the tool works
with both the current source layout and older gui-qml history. Use repeated
`--path-map SOURCE:TARGET` flags to override that.

## `add_filter_branch_metadata.py`

Creates a new branch whose tree and topology match a filtered target branch, but
with `Github-Pull:` and `Rebased-From:` trailers added to commits that were
copied from the source branch.

Typical use for the qt6 filtered import:

```bash
git clone git@github.com:bitcoin-core/gui-qml.git gui-qml-staging-work
(
  cd gui-qml-staging-work
  git fetch origin main qt6 qt6-dev
  ../add_filter_branch_metadata.py --switch
)
```

Dry-run the commit mapping first:

```bash
(
  cd gui-qml-staging-work
  ../add_filter_branch_metadata.py --dry-run
)
```

The defaults assume the script is run from a clean `gui-qml-staging-work` clone
inside this maintainer-tools checkout. They use:

```text
--source .
--source-ref origin/main
--target .
--target-ref origin/qt6
--target-import-tip 39eb251ad740271bf10820920275e90f219a0290
--tag-target-descendants
--branch qt6-main-provenance-trailers
```

Post-import commits that do not belong to a `Merge bitcoin-core/gui-qml#...`
context are listed during the run and receive only `Rebased-From:`. Pass
`--no-tag-target-descendants` for import-only tagging, or pass
`--target-import-tip auto` to find the import tip by matching the source tip
subject instead of using the qt6 import-tip default.

The default path maps are `src/qml:qml` and `qml:qml`. The script matches
non-merge commits by stable patch-id after rewriting diff header paths, matches
merge commits by `Merge bitcoin-core/gui-qml#...` subjects, can tag target-only
descendants with their existing commit hash as `Rebased-From:`, and verifies the
rewritten branch has the same tree as the original target ref.

## `filter_branch_for_staging.py`

Creates a new branch from a gui-qml branch with paths rewritten for staging
integration:

```text
qml/             -> src/qml/
test/functional/ -> test/functional/
test/*           -> src/qml/test/*
```

All other paths are dropped. Commits whose filtered tree is unchanged from their
single surviving parent are pruned by default. Rewritten commits are stamped
with the minimal staging provenance trailers: `Rebased-From:` and
`Github-Pull:`. `Github-Pull:` is added when the commit belongs to a
`Merge bitcoin-core/gui-qml#...` first-parent PR context. `Rebased-From:`
points to the gui-qml source commit hash being rewritten, so it can be used as
a direct lookup back to the original change. When filtering a branch prepared
by `add_filter_branch_metadata.py`, pass `--trust-source-provenance` to carry
that branch's two-stage `Github-Pull:` and `Rebased-From:` trailers forward.

Typical full staging import from the source checkout:

```bash
(
  cd gui-qml-staging-work
  ../filter_branch_for_staging.py --switch
)
```

The defaults assume `add_filter_branch_metadata.py` already created
`qt6-main-provenance-trailers` and that `fork/staging` is the local staging
base. They use:

```text
--source-ref qt6-main-provenance-trailers
--branch qt6-src-qml-on-staging
--linear-pr-history
--drop-pr-merge-boundaries
--trust-source-provenance
--base-ref refs/heads/fork/staging
```

For a compact branch that will be rebased onto a staging branch with regular
`git rebase`, generate a linear first-parent import stream instead of preserving
the filtered merge topology:

```bash
(
  cd gui-qml-staging-work
  ../filter_branch_for_staging.py \
    --source-ref origin/qt6 \
    --branch qt6-src-qml-first-parent \
    --linear-first-parent \
    --no-base-ref \
    --switch

  git rebase --root --onto refs/heads/fork/staging
)
```

This avoids conflicts caused by normal rebase flattening side-branch commits
from different gui-qml PRs onto each other. Each retained commit represents the
filtered tree change along gui-qml first-parent history, so PR merge results are
applied in maintainer order. This compact mode does not preserve the individual
PR-side commits, so it should not be used for a final staging branch where
GitHub contribution attribution matters.

For the full staging branch, first prepare qt6 with two-stage provenance. The
commits through the PR 450 filtered import are mapped back to the historical
main branch source commits, while qt6-only descendants get `Rebased-From:`
trailers pointing to their qt6 commit hashes:

```bash
(
  cd gui-qml-staging-work
  ../add_filter_branch_metadata.py --switch
)
```

Then build a single-parent staging import that keeps the reviewed PR-side
commits but does not recreate or carry over the first-parent
`Merge bitcoin-core/gui-qml#...` commits. The linear PR history mode applies
the PR-side commits in maintainer order; `--drop-pr-merge-boundaries` omits the
merge-result boundary commits from the generated staging branch.

To avoid the rebase step entirely, build the filtered branch directly on top of
the staging base. The filter overlays only paths that came from gui-qml, so
staging-owned files such as `src/qml/CMakeLists.txt` and `src/qml/main.cpp`
remain in the tree:

```bash
(
  cd gui-qml-staging-work
  ../filter_branch_for_staging.py --switch
)
```

`--linear-pr-history` is an alias for the older `--expand-pr-side-commits`
mode. Use `--preserve-pr-merges` only when you specifically want review chunks
as recreated two-parent merge commits. Use `--retitle-pr-merge-boundaries`
instead of `--drop-pr-merge-boundaries` only when you want to keep the
merge-result boundary commits while avoiding `Merge ...` subjects. Use
`--keep-pr-merge-boundaries` to keep the existing one-parent merge-result
boundary commits in the default linear PR history mode.

## Staging CMake patch series

The staging branch also needs CMake-only commits inserted around the filtered
QML history. The repeatable patch series lives in
`patches/staging-cmake-sequence/`, with a `series` file and insertion-point
notes in that directory's README.

For the full sequence from `origin/qt6-dev` to the complete staging branch, see
`docs/staging-branch-sequence.md`. The staging-base commits are captured in
`patches/staging-bootstrap/`.
