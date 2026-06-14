# staging branch sequence

This is the repeatable sequence for building the complete staging branch from
`origin/qt6-dev`.

## 1. Create the staging base

Apply the bootstrap patch series:

```bash
cd ../gui-qml-qt6
git switch -c fork/staging origin/qt6-dev
git am --whitespace=nowarn $(sed 's#^#../gui-qml-maintainer-tools/patches/staging-bootstrap/#' ../gui-qml-maintainer-tools/patches/staging-bootstrap/series)
```

This produces the staging-only base commits that prepare Qt/QML dependencies,
add the `bitcoin-qml` bootstrap executable, and wire `src/qml` from the parent
`src/CMakeLists.txt`.

Use `git am` for patch replay so the original commit author and author date are
retained from the `git format-patch` headers. Avoid `git apply` plus a fresh
`git commit` unless you explicitly restore `GIT_AUTHOR_NAME`,
`GIT_AUTHOR_EMAIL`, and `GIT_AUTHOR_DATE`.

## 2. Select gui-qml source history

Fetch the gui-qml source history that should be imported:

```bash
cd ../gui-qml-qt6
git fetch origin qt6 qt6-dev
```

Prepare the qt6 provenance branch in two stages. Commits through the PR 450
filtered import are mapped back to the historical main branch source commits.
Commits after that import tip are qt6-only commits, so their `Rebased-From:`
trailers point to the qt6 commit hashes themselves.

```bash
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

## 3. Filter gui-qml paths onto staging

Build the filtered import directly on top of the staging base:

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

Use `--preserve-pr-merges` for the complete staging branch. It rewrites the
PR-side commits onto a side branch, then recreates each
`Merge bitcoin-core/gui-qml#...` commit as a real two-parent merge. The recreated
merge uses the filtered original merge tree as the resolved result, so conflicts
already resolved in reviewed gui-qml PR merges do not have to be rediscovered by
a later linear rebase.

The older `--expand-pr-side-commits` mode keeps PR-side author commits but
linearizes the merge boundary, so it can expose conflicts that the original PR
merge had already resolved. `--linear-first-parent` remains useful only for
compact/audit branches where individual PR-side commits are intentionally
collapsed.

The filter rules are:

```text
qml/             -> src/qml/
test/functional/ -> test/functional/
test/*           -> src/qml/test/*
all other paths  -> dropped
```

## 4. Insert staging CMake commits

Use `patches/staging-cmake-sequence/series` while rewriting the filtered
branch. The intended placement is documented in that directory. In short:

```text
0001 amend staging bootstrap commit `cmake: Add bitcoin-qml executable`
0002 insert after `qml: Add stub window`
0003 insert after `Merge bitcoin-core/gui-qml#11: Add basic start/shutdown functionality`
0004 insert after `Merge bitcoin-core/gui-qml#497: Add first unittests`
0005 insert after `Merge bitcoin-core/gui-qml#536: Lang units settings`
```

When starting from `patches/staging-bootstrap`, patch `0001` is already included
in the staging base. The remaining CMake sequence patches are inserted as new
commits around the filtered gui-qml commits that make each CMake change
necessary.

For manually amended checkpoints, preserve the existing author by using
`git commit --amend --no-edit` and do not pass `--reset-author`.

If any insertion or rewrite step stops for a conflict, document the manual
resolution in `patches/staging-cmake-sequence/conflict-resolutions.md` before
continuing the sequence. Each entry should identify the operation, the patch or
source commit being applied, the conflicting paths, the staging-specific
decision, and the validation command that covered the result.

Current verified snapshot:

```text
origin/qt6-dev              27472a542c
fork/staging                12b5c02698
qt6-main-provenance-trailers 3dac81b11c
qt6-src-qml-on-staging  f9658a1774
qt6-src-qml-on-staging-cmake 78b833601b
```

## 5. Validate

Basic configure checkpoint:

```bash
cmake -S ../gui-qml-qt6 -B /tmp/gui-qml-cmake-seq-build -GNinja \
  -DBUILD_GUI=ON \
  -DBUILD_TESTS=OFF \
  -DBUILD_GUI_TESTS=OFF \
  -DENABLE_WALLET=ON \
  -DWITH_QRENCODE=OFF \
  -DENABLE_IPC=OFF \
  -DWITH_ZMQ=OFF
```

Build checkpoint:

```bash
cmake --build /tmp/gui-qml-cmake-seq-build --target bitcoin-qml -j"$(nproc)"
```

As of this sequence snapshot, configure succeeds. The `bitcoin-qml` build gets
past QML/translation resource generation and then fails in Qt 6.4 automoc on
`src/qml/models/chainmodel.h`, because moc parses a GCC 13 standard library
`<concept>` include and errors at `std`. The unsequenced
`patches/staging-cmake-sequence/0006-qml-avoid-moc-parsing-core-headers.patch`
records that staging-layout fix; choose its insertion point near the commit that
introduces `chainmodel.h`.
