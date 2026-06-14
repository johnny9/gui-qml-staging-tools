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

## 2. Prepare provenance-tagged gui-qml history

If the provenance-tagged source branch already exists, reuse it. Otherwise:

```bash
cd ../gui-qml-qt6
../gui-qml-maintainer-tools/add_filter_branch_metadata.py \
  --source ../gui-qml-main \
  --target-ref qt6 \
  --target-import-tip 39eb251ad740271bf10820920275e90f219a0290 \
  --tag-target-descendants \
  --branch codex/qt6-main-provenance-trailers \
  --switch
```

The output branch should retain `Github-Pull:`, `Rebased-From:`, and
`Original-gui-qml-*` provenance trailers.

## 3. Filter gui-qml paths onto staging

Build the filtered import directly on top of the staging base:

```bash
cd ../gui-qml-qt6
../gui-qml-maintainer-tools/filter_branch_for_staging.py \
  --source-ref codex/qt6-main-provenance-trailers \
  --branch codex/qt6-src-qml-on-staging \
  --expand-pr-side-commits \
  --base-ref refs/heads/fork/staging \
  --switch
```

Use `--expand-pr-side-commits` for the complete staging branch. It keeps the
linear staging import shape, but expands each `Merge bitcoin-core/gui-qml#...`
commit into the PR-side commits first and then keeps the PR merge boundary. This
preserves the original PR commit authors for GitHub contribution attribution.
The older `--linear-first-parent` mode is only for compact/audit branches where
the PR merge result is enough and individual PR-side commits are intentionally
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
fork/staging                cba6358c1b
codex/qt6-src-qml-on-staging bda728de92
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
`<concepts>` include and errors at `std`. That remaining fix should be handled
near the commit that introduces `chainmodel.h`.
