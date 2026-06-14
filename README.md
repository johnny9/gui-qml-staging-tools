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
cd ../gui-qml-qt6
../gui-qml-maintainer-tools/add_filter_branch_metadata.py \
  --source ../gui-qml-main \
  --target-ref qt6 \
  --target-import-tip 39eb251ad740271bf10820920275e90f219a0290 \
  --branch qt6-main-provenance-trailers \
  --switch
```

Dry-run the commit mapping first:

```bash
../gui-qml-maintainer-tools/add_filter_branch_metadata.py \
  --source ../gui-qml-main \
  --target-ref qt6 \
  --target-import-tip 39eb251ad740271bf10820920275e90f219a0290 \
  --dry-run
```

To also tag commits after the filtered import tip, using PR context from the
target branch's own merge commits:

```bash
../gui-qml-maintainer-tools/add_filter_branch_metadata.py \
  --source ../gui-qml-main \
  --target-ref qt6 \
  --target-import-tip 39eb251ad740271bf10820920275e90f219a0290 \
  --tag-target-descendants \
  --branch qt6-main-provenance-trailers \
  --switch
```

Post-import commits that do not belong to a `Merge bitcoin-core/gui-qml#...`
context are listed during the run and receive only `Rebased-From:`.

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

Typical use from the source checkout:

```bash
cd ../gui-qml-qt6
../gui-qml-maintainer-tools/filter_branch_for_staging.py \
  --source-ref origin/qt6 \
  --branch qt6-src-qml-filtered \
  --switch
```

For a compact branch that will be rebased onto a staging branch with regular
`git rebase`, generate a linear first-parent import stream instead of preserving
the filtered merge topology:

```bash
cd ../gui-qml-qt6
../gui-qml-maintainer-tools/filter_branch_for_staging.py \
  --source-ref origin/qt6 \
  --branch qt6-src-qml-first-parent \
  --linear-first-parent \
  --switch

git rebase --root --onto refs/heads/fork/staging
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
cd ../gui-qml-qt6
../gui-qml-maintainer-tools/add_filter_branch_metadata.py \
  --source ../gui-qml \
  --source-ref origin/main \
  --target . \
  --target-ref origin/qt6 \
  --target-import-tip 39eb251ad740271bf10820920275e90f219a0290 \
  --tag-target-descendants \
  --allow-subject-fallback \
  --branch qt6-main-provenance-trailers \
  --switch
```

Then preserve each gui-qml PR as a chunk. This rewrites the PR-side commits
onto a side branch, then recreates the reviewed PR merge as a real two-parent
merge commit. The recreated merge uses the filtered original merge tree as the
resolved result, so conflicts already worked out in gui-qml merge commits are
not rediscovered by a later linear rebase:

To avoid the rebase step entirely, build the filtered branch directly on top of
the staging base. The filter overlays only paths that came from gui-qml, so
staging-owned files such as `src/qml/CMakeLists.txt` and `src/qml/main.cpp`
remain in the tree:

```bash
cd ../gui-qml-qt6
../gui-qml-maintainer-tools/filter_branch_for_staging.py \
  --source-ref qt6-main-provenance-trailers \
  --branch qt6-src-qml-on-staging \
  --preserve-pr-merges \
  --trust-source-provenance \
  --base-ref refs/heads/fork/staging \
  --switch
```

`--expand-pr-side-commits` remains available for a linear import that keeps
PR-side commit authorship, but it does not preserve real merge topology and can
surface conflicts that the original PR merge commit had already resolved.

## Staging CMake patch series

The staging branch also needs CMake-only commits inserted around the filtered
QML history. The repeatable patch series lives in
`patches/staging-cmake-sequence/`, with a `series` file and insertion-point
notes in that directory's README.

For the full sequence from `origin/qt6-dev` to the complete staging branch, see
`docs/staging-branch-sequence.md`. The staging-base commits are captured in
`patches/staging-bootstrap/`.
