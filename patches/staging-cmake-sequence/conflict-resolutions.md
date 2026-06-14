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

### Remap imported QML test CMake paths

- Operation: `git am --3way`
- Applying: `0004-cmake-wire-qml-tests-from-src-qml.patch`
- Onto: `62e3ee739a3b6332bb795587f29e2b8efadc6699 cmake: Build QML sources from src/qml`
- Conflicting paths:
  - `src/qml/test/CMakeLists.txt`
- Resolution:
  - Kept the full imported gui-qml test target contents, including the newer unit
    tests and QML test helper sources.
  - Kept the staging patch's intent to enter `src/qml/test` from
    `src/qml/CMakeLists.txt`.
  - Remapped the remaining old source-tree references from `../qml` and
    `../bitcoin/src` to `${PROJECT_SOURCE_DIR}/src/qml`,
    `${PROJECT_SOURCE_DIR}/src`, `${PROJECT_SOURCE_DIR}/src/univalue/include`,
    and `${PROJECT_BINARY_DIR}/src`.
- Reason: The filtered import already contains the current test inventory, while
  staging needs those tests to reference the integrated Bitcoin Core tree layout
  instead of the old gui-qml checkout layout.
- Validation:
  - `cmake -S /home/johnny/github/gui-qml-qt6-staging-attempt -B /tmp/gui-qml-preserve-build -GNinja -DBUILD_GUI=ON -DBUILD_TESTS=OFF -DBUILD_GUI_TESTS=OFF -DENABLE_WALLET=ON -DWITH_QRENCODE=OFF -DENABLE_IPC=OFF -DWITH_ZMQ=OFF` succeeded.
  - `cmake --build /tmp/gui-qml-preserve-build --target bitcoin-qml -j$(nproc)`
    reached QML resource/translation generation and then failed in Qt 6.4
    automoc on `src/qml/models/chainmodel.h` with `usr/include/c++/13/concept:46:1:
    error: Parse error at "std"`.
