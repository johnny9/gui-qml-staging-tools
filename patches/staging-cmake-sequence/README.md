# staging CMake sequence

This directory contains staging-only CMake commits for replaying the filtered
`src/qml` history on top of the staging branch.

Apply each patch at the listed checkpoint with `git am` while rewriting the
branch:

`git am` preserves the author and author date from these `git format-patch`
files. Do not convert the patches to `git apply` plus `git commit`; if a commit
must be amended manually, use `git commit --amend --no-edit` without
`--reset-author`.

| Patch | Checkpoint |
| --- | --- |
| `0001-cmake-add-bitcoinqml-bootstrap.patch` | Amend the staging commit `cmake: Add \`bitcoin-qml\` executable`. |
| `0002-cmake-embed-qml-resources.patch` | Insert after `qml: Add stub window`. |
| `0003-cmake-build-qml-sources-from-src-qml.patch` | Insert after `Merge bitcoin-core/gui-qml#11: Add basic start/shutdown functionality`. |
| `0004-cmake-wire-qml-tests-from-src-qml.patch` | Insert after `Merge bitcoin-core/gui-qml#497: Add first unittests`. |
| `0005-cmake-embed-qml-translations.patch` | Insert after `Merge bitcoin-core/gui-qml#536: Lang units settings`. |

The first patch is an amended replacement for the bootstrap CMake commit. The
remaining patches are new commits inserted next to the gui-qml commits that make
their CMake wiring necessary.

`0006-qml-avoid-moc-parsing-core-headers.patch` is an unsequenced staging-layout
fix for the Qt automoc failure in `src/qml/models/chainmodel.h`. Choose its
insertion point near the commit that introduces `ChainModel` before adding it to
`series`.

If replaying or inserting these patches requires a manual conflict resolution,
record it in `conflict-resolutions.md` before moving on to the next patch. The
entry should name the operation, the patch or source commit being applied, the
conflicting paths, the staging-specific resolution, and the validation command
that covered it.
