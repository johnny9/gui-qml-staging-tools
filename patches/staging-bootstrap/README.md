# staging bootstrap patches

These patches recreate the local staging base on top of `origin/qt6-dev`.

Current expected first-parent range:

```text
cba6358c1b cmake: Incorporate `qml` subdirectory
19bb14da88 cmake: Add `bitcoin-qml` executable
09508f4d1c depends: Add Qt Qml and Qt Quick modules
51c7877a13 cmake: Require Qt Qml and Qt Quick modules when `BUILD_GUI=ON`
6a8085d2f9 scripted-diff: Rename UNIQUE_NAME to BITCOIN_UNIQUE_NAME
```

To recreate the staging base:

```bash
cd ../gui-qml-qt6
git switch -c fork/staging origin/qt6-dev
git am --whitespace=nowarn $(sed 's#^#../gui-qml-maintainer-tools/patches/staging-bootstrap/#' ../gui-qml-maintainer-tools/patches/staging-bootstrap/series)
```

Use `git am`, not `git apply` followed by a new commit. The patch files were
created with `git format-patch`, so `git am` preserves the original commit
author and author date from each patch.

Patch `0004-cmake-Add-bitcoin-qml-executable.patch` includes the amended
bootstrap CMake structure that creates the `bitcoinqml` static library. It is
intentionally aligned with `patches/staging-cmake-sequence/0001-*`.
