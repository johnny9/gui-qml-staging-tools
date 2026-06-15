# staging branch build-fix ledger

This file records fixes discovered while walking the first-parent
`gui-qml-staging/qml-staging` branch against the current staging/Core tree.

The goal is to make the rewrite reproducible: each section names the broken
checkpoint commit, the failure, the later commit or current Core API where the
fix was found, the patch shape to amend into the broken commit, and the build
validation that covered it.

Build command used for checkpoints:

```bash
export CCACHE_BASEDIR=/home/johnny/github
export CCACHE_DIR=/home/johnny/.cache/ccache
cmake -S /home/johnny/github/gui-staging-branch-creation/gui-qml-staging \
  -B /tmp/gui-qml-staging-buildwalk -GNinja \
  -DBUILD_GUI=ON \
  -DBUILD_TESTS=OFF \
  -DBUILD_GUI_TESTS=OFF \
  -DENABLE_WALLET=ON \
  -DWITH_QRENCODE=OFF \
  -DENABLE_IPC=OFF \
  -DWITH_ZMQ=OFF
cmake --build /tmp/gui-qml-staging-buildwalk --target bitcoin-qml -j"$(nproc)"
```

Walk completion:

- Completed the first-parent walk through `78b833601b` on
  `fork/qml-staging`.
- Final accumulated patch:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-303-78b833601b.patch`.
- Local `gui-qml-staging` branch `qml-staging` now tracks
  `fork/qml-staging` at `78b833601b` with the final fix overlay in the
  worktree.

## `3c14dd1356` - `cmake: Embed QML resources`

Status:

- Patch application failed at first-parent position 300 after applying
  `fix-through-299-f9658a1774.patch`.
- The commit introduced explicit QML resource embedding, while the accumulated
  CMake patch expected the pre-resource `bitcoin.cpp`-only target.
- Builds after applying `fix-through-299-f9658a1774.patch` while excluding
  `src/qml/CMakeLists.txt`, then applying the CMake patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-300-3c14dd1356.patch`.

Failure:

- The `add_library(bitcoinqml STATIC bitcoin.cpp)` context was replaced by
  resource-generation lines before the later source-list/test-wiring fix could
  apply.
- The current build needs the later recursive QML source list and link
  libraries immediately, otherwise source files added before the CMake source
  list commit are not compiled into `bitcoinqml`.

Fix sources:

- `a64844ecc7 cmake: Build QML sources from src/qml` supplies the recursive QML
  source discovery, test-automation define, and added link libraries.
- `3b7cfd11f4 cmake: Wire QML tests from src/qml` supplies the conditional test
  subdirectory.
- `78b833601b cmake: Embed QML translations` is intentionally not included
  here; it belongs to the later translation-resource commit.

Patch to amend into `3c14dd1356` after carrying
`fix-through-299-f9658a1774.patch` except `src/qml/CMakeLists.txt`:

```diff
diff --git a/src/qml/CMakeLists.txt b/src/qml/CMakeLists.txt
--- a/src/qml/CMakeLists.txt
+++ b/src/qml/CMakeLists.txt
@@
 set(CMAKE_AUTOMOC ON)

-add_library(bitcoinqml STATIC
-  bitcoin.cpp
-)
+option(ENABLE_TEST_AUTOMATION "Enable test automation bridge for QML UI testing" OFF)

 set(QML_QRC "${CMAKE_CURRENT_SOURCE_DIR}/bitcoin_qml.qrc")
 qt6_add_resources(QML_QRC_CPP ${QML_QRC})
-target_sources(bitcoinqml
-  PRIVATE
-    ${QML_QRC_CPP}
+
+file(GLOB_RECURSE QML_SOURCES
+  "${CMAKE_CURRENT_SOURCE_DIR}/*.cpp"
+  "${CMAKE_CURRENT_SOURCE_DIR}/*.h"
 )
+list(FILTER QML_SOURCES EXCLUDE REGEX "/main\\.cpp$")
+list(FILTER QML_SOURCES EXCLUDE REGEX "/androidnotifier\\.(cpp|h)$")
+if(NOT ENABLE_TEST_AUTOMATION)
+  list(FILTER QML_SOURCES EXCLUDE REGEX "/test/")
+endif()
+list(APPEND QML_SOURCES ${QML_QRC_CPP})
+
+add_library(bitcoinqml STATIC ${QML_SOURCES})
@@
 target_compile_definitions(bitcoinqml
   PUBLIC
     QT_NO_KEYWORDS
     QT_USE_QSTRINGBUILDER
 )
+if(ENABLE_TEST_AUTOMATION)
+  target_compile_definitions(bitcoinqml PUBLIC ENABLE_TEST_AUTOMATION)
+endif()
@@
 target_link_libraries(bitcoinqml
   PUBLIC
     core_interface
     bitcoin_node
+    univalue
+    Boost::headers
+    $<TARGET_NAME_IF_EXISTS:QRencode::QRencode>
     Qt6::Qml
-    Qt6::Widgets
     Qt6::Quick
+    Qt6::QuickControls2
+    Qt6::Network
+    Qt6::Widgets
 )
@@
 install_binary_component(bitcoin-qml)

+if(BUILD_GUI_TESTS)
+  add_subdirectory(test)
+endif()
+
 # Use the `bitcoin-qml` target as a drop-in replacement
```

## `f9658a1774` - `Merge bitcoin-core/gui-qml#736: A bunch of fixes for Preview release target`

Status:

- `fix-through-297-39e3dff592.patch` built cleanly through
  `cf0d7f4539`.
- Patch application failed at first-parent position 299 because PR #736
  rewrites `WalletQmlModel` around Send fee previews, selected inputs, URI
  import, receive-request compatibility, and external-signer handling.
- Builds after applying `fix-through-297-39e3dff592.patch` while excluding
  `src/qml/models/walletqmlmodel.cpp`, then applying the wallet patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-299-f9658a1774.patch`.

Failure:

- The previous checkpoint expected the PR #708 wallet model layout.
- The #736 wallet model still used stale `createTransaction`, `getAddress`,
  wallet ownership, transaction-changed callback, and `fillPSBT` call sites.

Fix sources:

- `d7b35d9c7c qml: adapt wallet transaction creation API` supplies the
  `createTransaction` result-object changes.
- `e426705a4d qml: adapt wallet ownership and metadata APIs` supplies the
  boolean ownership and `getAddress` changes.
- Current `interfaces::Wallet::handleTransactionChanged` passes `Txid`, so the
  QML model adapter converts it back to `uint256` for existing QML consumers.
- Current `interfaces::Wallet::fillPSBT` takes `wallet::PSBTFillOptions`.

Patch to amend into `f9658a1774` after carrying
`fix-through-297-39e3dff592.patch` except
`src/qml/models/walletqmlmodel.cpp`:

```diff
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@
 std::optional<CAmount> TryPreviewFee(interfaces::Wallet& wallet,
                                      const std::vector<wallet::CRecipient>& recipients,
                                      const wallet::CCoinControl& coin_control)
 {
-    int change_position{-1};
-    CAmount fee{0};
-    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, change_position, fee);
+    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, /*change_pos=*/std::nullopt);
     if (!result) {
         return std::nullopt;
     }

-    return fee;
+    return result->fee;
 }
@@
-    if (m_wallet->getAddress(destination, &label, nullptr, nullptr)) {
+    if (m_wallet->getAddress(destination, &label, nullptr)) {
@@
-    if (!m_wallet->getAddress(destination, nullptr, nullptr, &purpose)) {
+    if (!m_wallet->getAddress(destination, nullptr, &purpose)) {
@@
-        if (wallet_address.purpose != wallet::AddressPurpose::RECEIVE || wallet_address.is_mine == wallet::ISMINE_NO) {
+        if (wallet_address.purpose != wallet::AddressPurpose::RECEIVE || !wallet_address.is_mine) {
             continue;
         }
@@
-    return m_wallet->handleTransactionChanged(fn);
+    return m_wallet->handleTransactionChanged([fn = std::move(fn)](const Txid& txid, ChangeType status) {
+        fn(txid.ToUint256(), status);
+    });
 }
@@
-    int nChangePosRet = -1;
-    CAmount nFeeRequired = 0;
     const bool sign = !m_wallet->privateKeysDisabled();
-    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, sign, nChangePosRet, nFeeRequired);
+    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, sign, /*change_pos=*/std::nullopt);
     if (result) {
@@
-        const CTransactionRef& newTx = *result;
+        const CTransactionRef& newTx = result->tx;
@@
-        m_current_transaction->setTransactionFee(nFeeRequired);
+        m_current_transaction->setTransactionFee(result->fee);
         if (subtract_fee_from_amount) {
-            m_current_transaction->reassignAmounts(nChangePosRet);
+            m_current_transaction->reassignAmounts(static_cast<int>(result->change_pos.value_or(-1)));
         }
@@
-        const auto draft_err = m_wallet->fillPSBT(std::nullopt, /*sign=*/false, /*bip32derivs=*/true,
+        const auto draft_err = m_wallet->fillPSBT({.sign = false, .bip32_derivs = true},
             /*n_signed=*/nullptr, psbtx, complete);
@@
-        const auto sign_err = m_wallet->fillPSBT(std::nullopt, /*sign=*/true, /*bip32derivs=*/true,
+        const auto sign_err = m_wallet->fillPSBT({.sign = true, .bip32_derivs = true},
             /*n_signed=*/nullptr, psbtx, complete);
```

## `39e3dff592` - `Merge bitcoin-core/gui-qml#724: Node status (mini blockclock) and runtime feedback (Errors/Warnings)`

Status:

- Patch application succeeded at first-parent position 297 with
  `fix-through-296-fc26659cd3.patch`.
- Build failed in the newly introduced runtime-dialog and node-information
  surfaces from PR #724.
- Builds after applying the focused runtime-dialog callback and uptime patch
  below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-297-39e3dff592.patch`.

Failure:

- `QmlGuiMain()` still connected `ThreadSafeMessageBox` with the old
  `(message, caption, style)` callback shape.
- `NodeModel::ConnectToRuntimeDialogSignals()` still connected
  `handleMessageBox` and `handleQuestion` with caption parameters.
- `NodeModel::showRuntimeDialog*()` and `RuntimeDialogRequest` still carried a
  caption even though current Core no longer provides one.
- `NodeModel::nodeInformationRows()` used removed `GetStartupTime()`.

Fix sources:

- `3128421c22 qml: adapt runtime dialog callbacks to Core v31` provides the
  runtime-dialog callback updates.
- Current `node/interface_ui.h` and `interfaces/node.h` expose message and
  question callbacks without captions.
- Current `util/time.h` exposes `GetUptime()` and `TicksSeconds()` for deriving
  startup time.

Patch to amend into `39e3dff592` after carrying
`fix-through-296-fc26659cd3.patch`:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
--- a/src/qml/bitcoin.cpp
+++ b/src/qml/bitcoin.cpp
@@
-bool InitErrorMessageBox(
-    const bilingual_str& message,
-    [[maybe_unused]] const std::string& caption,
-    [[maybe_unused]] unsigned int style)
+bool InitErrorMessageBox(
+    const bilingual_str& message,
+    [[maybe_unused]] unsigned int style)
@@
     auto handler_message_box = ::uiInterface.ThreadSafeMessageBox_connect(
-        [&startup_warnings](const bilingual_str& message, const std::string& caption, unsigned int style) {
+        [&startup_warnings](const bilingual_str& message, unsigned int style) {
             if (style & CClientUIInterface::ICON_WARNING) {
                 RecordStartupWarning(startup_warnings, message);
                 return false;
             }
-            return InitErrorMessageBox(message, caption, style);
+            return InitErrorMessageBox(message, style);
         });
diff --git a/src/qml/models/nodemodel.cpp b/src/qml/models/nodemodel.cpp
--- a/src/qml/models/nodemodel.cpp
+++ b/src/qml/models/nodemodel.cpp
@@
-QString RuntimeDialogTitle(const QString& caption, unsigned int style)
+QString RuntimeDialogTitle(unsigned int style)
 {
-    if (!caption.isEmpty()) {
-        return caption;
-    }
@@
-    showRuntimeDialogOnGuiThread(warnings, QString{}, CClientUIInterface::ICON_WARNING, /*question=*/false);
+    showRuntimeDialogOnGuiThread(warnings, CClientUIInterface::ICON_WARNING, /*question=*/false);
@@
     m_handler_message_box = m_node.handleMessageBox(
-        [this](const bilingual_str& message, const std::string& caption, unsigned int style) {
+        [this](const bilingual_str& message, unsigned int style) {
             return showRuntimeDialog(
                 QString::fromStdString(message.translated),
-                QString::fromStdString(caption),
                 style,
                 /*question=*/false);
         });
     m_handler_question = m_node.handleQuestion(
-        [this](const bilingual_str& message, [[maybe_unused]] const std::string& non_interactive_message, const std::string& caption, unsigned int style) {
+        [this](const bilingual_str& message, [[maybe_unused]] const std::string& non_interactive_message, unsigned int style) {
             return showRuntimeDialog(
                 QString::fromStdString(message.translated),
-                QString::fromStdString(caption),
                 style,
                 /*question=*/true);
         });
@@
-    rows.push_back(InformationRow(tr("Startup time"), QDateTime::fromSecsSinceEpoch(GetStartupTime()).toString()));
+    rows.push_back(InformationRow(tr("Startup time"), QDateTime::currentDateTime().addSecs(-TicksSeconds(GetUptime())).toString()));
@@
-bool NodeModel::showRuntimeDialog(const QString& message, const QString& caption, unsigned int style, bool question)
+bool NodeModel::showRuntimeDialog(const QString& message, unsigned int style, bool question)
 {
     if (QThread::currentThread() == thread()) {
-        return showRuntimeDialogOnGuiThread(message, caption, style, question);
+        return showRuntimeDialogOnGuiThread(message, style, question);
     }

     if (!(style & CClientUIInterface::MODAL) && !question) {
-        QMetaObject::invokeMethod(this, [this, message, caption, style, question] {
-            showRuntimeDialogOnGuiThread(message, caption, style, question);
+        QMetaObject::invokeMethod(this, [this, message, style, question] {
+            showRuntimeDialogOnGuiThread(message, style, question);
         }, Qt::QueuedConnection);
         return false;
     }

     bool result{false};
-    QMetaObject::invokeMethod(this, [this, &result, message, caption, style, question] {
-        result = showRuntimeDialogOnGuiThread(message, caption, style, question);
+    QMetaObject::invokeMethod(this, [this, &result, message, style, question] {
+        result = showRuntimeDialogOnGuiThread(message, style, question);
     }, Qt::BlockingQueuedConnection);
     return result;
 }

-bool NodeModel::showRuntimeDialogOnGuiThread(const QString& message, const QString& caption, unsigned int style, bool question)
+bool NodeModel::showRuntimeDialogOnGuiThread(const QString& message, unsigned int style, bool question)
@@
     auto request{std::make_shared<RuntimeDialogRequest>()};
     request->message = message;
-    request->caption = caption;
@@
-    m_runtime_dialog_title = RuntimeDialogTitle(request->caption, request->style);
+    m_runtime_dialog_title = RuntimeDialogTitle(request->style);
@@
-void NodeModel::showRuntimeDialogForTest(const QString& message, const QString& caption, unsigned int style, bool question)
+void NodeModel::showRuntimeDialogForTest(const QString& message, unsigned int style, bool question)
 {
     auto request{std::make_shared<RuntimeDialogRequest>()};
     request->message = message;
-    request->caption = caption;
diff --git a/src/qml/models/nodemodel.h b/src/qml/models/nodemodel.h
--- a/src/qml/models/nodemodel.h
+++ b/src/qml/models/nodemodel.h
@@
-    Q_INVOKABLE void showRuntimeDialogForTest(const QString& message, const QString& caption, unsigned int style, bool question);
+    Q_INVOKABLE void showRuntimeDialogForTest(const QString& message, unsigned int style, bool question);
@@
     struct RuntimeDialogRequest {
         QString message;
-        QString caption;
@@
-    bool showRuntimeDialog(const QString& message, const QString& caption, unsigned int style, bool question);
-    bool showRuntimeDialogOnGuiThread(const QString& message, const QString& caption, unsigned int style, bool question);
+    bool showRuntimeDialog(const QString& message, unsigned int style, bool question);
+    bool showRuntimeDialogOnGuiThread(const QString& message, unsigned int style, bool question);
```

## `fc26659cd3` - `Merge bitcoin-core/gui-qml#708: Activity filtering and Receive request`

Status:

- Patch application failed at first-parent position 296 after applying
  `fix-through-295-fa11450dc5.patch`.
- The merge rewrites `WalletQmlModel` around receive-request and activity
  filtering state, so the accumulated wallet API hunks must be re-applied in
  the new file shape.
- Builds after applying `fix-through-295-fa11450dc5.patch` while excluding
  `src/qml/models/walletqmlmodel.cpp`, then applying the wallet patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-296-fc26659cd3.patch`.

Failure:

- The previous patch expected the PR #561 wallet model layout.
- The same stale `createTransaction`, `getAddress`, wallet ownership,
  transaction-changed callback, and `fillPSBT` call sites remain after the
  receive-request rewrite.

Fix sources:

- Same API fix sources as the prior wallet model rewrite boundaries:
  `d7b35d9c7c`, `e426705a4d`, `dc4a5d1270`, and `f77b90485d`.
- `fc26659cd3` introduces the receive-request layout that shifts the hunk
  context.

Patch to amend into `fc26659cd3` after carrying the rest of
`fix-through-295-fa11450dc5.patch`:

```diff
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
index c93a00790f..4f2377c372 100644
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@ -136,14 +136,12 @@ std::optional<CAmount> TryPreviewFee(interfaces::Wallet& wallet,
                                      const std::vector<wallet::CRecipient>& recipients,
                                      const wallet::CCoinControl& coin_control)
 {
-    int change_position{-1};
-    CAmount fee{0};
-    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, change_position, fee);
+    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, /*change_pos=*/std::nullopt);
     if (!result) {
         return std::nullopt;
     }

-    return fee;
+    return result->fee;
 }
@@ -932,7 +930,7 @@ QString WalletQmlModel::getAddressLabel(const QString& address) const
     }

     std::string label;
-    if (m_wallet->getAddress(destination, &label, nullptr, nullptr)) {
+    if (m_wallet->getAddress(destination, &label, nullptr)) {
         if (!label.empty()) {
             return QString::fromStdString(label);
         }
@@ -959,7 +957,7 @@ bool WalletQmlModel::setAddressLabel(const QString& address, const QString& labe
     }

     wallet::AddressPurpose purpose{wallet::AddressPurpose::RECEIVE};
-    if (!m_wallet->getAddress(destination, nullptr, nullptr, &purpose)) {
+    if (!m_wallet->getAddress(destination, nullptr, &purpose)) {
         return false;
     }
@@ -1007,7 +1005,7 @@ std::set<QString> WalletQmlModel::usedAddresses() const

     std::set<QString> receive_addresses;
     for (const interfaces::WalletAddress& wallet_address : getAddresses()) {
-        if (wallet_address.purpose != wallet::AddressPurpose::RECEIVE || wallet_address.is_mine == wallet::ISMINE_NO) {
+        if (wallet_address.purpose != wallet::AddressPurpose::RECEIVE || !wallet_address.is_mine) {
             continue;
         }
@@ -1082,7 +1080,9 @@ std::unique_ptr<interfaces::Handler> WalletQmlModel::handleTransactionChanged(Tr
     if (!m_wallet) {
         return nullptr;
     }
-    return m_wallet->handleTransactionChanged(fn);
+    return m_wallet->handleTransactionChanged([fn = std::move(fn)](const Txid& txid, ChangeType status) {
+        fn(txid.ToUint256(), status);
+    });
 }
@@ -1318,20 +1318,18 @@ bool WalletQmlModel::prepareTransactionInternal(std::optional<SecureString> pass
         return false;
     }

-    int nChangePosRet = -1;
-    CAmount nFeeRequired = 0;
     const bool sign = !m_wallet->privateKeysDisabled();
-    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, sign, nChangePosRet, nFeeRequired);
+    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, sign, /*change_pos=*/std::nullopt);
     if (result) {
         if (m_current_transaction) {
             delete m_current_transaction;
         }
-        const CTransactionRef& newTx = *result;
+        const CTransactionRef& newTx = result->tx;
         m_current_transaction = new WalletQmlModelTransaction(m_send_recipients, this);
         m_current_transaction->setWtx(newTx);
-        m_current_transaction->setTransactionFee(nFeeRequired);
+        m_current_transaction->setTransactionFee(result->fee);
         if (subtract_fee_from_amount) {
-            m_current_transaction->reassignAmounts(nChangePosRet);
+            m_current_transaction->reassignAmounts(static_cast<int>(result->change_pos.value_or(-1)));
         }
@@ -1362,7 +1360,7 @@ void WalletQmlModel::approveExternalSignerTransaction()
         PartiallySignedTransaction psbtx(mtx);
         bool complete = false;

-        const auto draft_err = m_wallet->fillPSBT(std::nullopt, /*sign=*/false, /*bip32derivs=*/true,
+        const auto draft_err = m_wallet->fillPSBT({.sign = false, .bip32_derivs = true},
             /*n_signed=*/nullptr, psbtx, complete);
@@ -1372,7 +1370,7 @@ void WalletQmlModel::approveExternalSignerTransaction()
             return;
         }

-        const auto sign_err = m_wallet->fillPSBT(std::nullopt, /*sign=*/true, /*bip32derivs=*/true,
+        const auto sign_err = m_wallet->fillPSBT({.sign = true, .bip32_derivs = true},
             /*n_signed=*/nullptr, psbtx, complete);
```

## `fa11450dc5` - `Merge bitcoin-core/gui-qml#561: Implement Addresses list and Sign/Verify in Wallet Settings`

Status:

- Patch application succeeded at first-parent position 295 with
  `fix-through-294-aab195f74c.patch`.
- Build failed in newly introduced address-list and wallet address-label code.
- Builds after applying the focused wallet metadata/ownership patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-295-fa11450dc5.patch`.

Failure:

- `AddressListModel` used removed `wallet::ISMINE_NO` and compared
  `WalletAddress::is_mine` as an `isminetype`.
- `WalletQmlModel::setAddressLabel()` called the old four-argument
  `getAddress` overload.
- `WalletQmlModel::usedAddresses()` also compared `is_mine` against
  `wallet::ISMINE_NO`.

Fix sources:

- `e426705a4d qml: adapt wallet ownership and metadata APIs` supplies these
  exact address ownership and metadata call-site updates.
- Current `interfaces::WalletAddress::is_mine` is boolean.
- Current `interfaces::Wallet::getAddress` takes destination, label pointer,
  and purpose pointer.

Patch to amend into `fa11450dc5` after carrying
`fix-through-294-aab195f74c.patch`:

```diff
diff --git a/src/qml/models/addresslistmodel.cpp b/src/qml/models/addresslistmodel.cpp
--- a/src/qml/models/addresslistmodel.cpp
+++ b/src/qml/models/addresslistmodel.cpp
@@
 using wallet::AddressPurpose;
-using wallet::ISMINE_NO;
@@
-        if (wallet_address.purpose != AddressPurpose::RECEIVE || wallet_address.is_mine == ISMINE_NO) {
+        if (wallet_address.purpose != AddressPurpose::RECEIVE || !wallet_address.is_mine) {
             continue;
         }
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@
     wallet::AddressPurpose purpose{wallet::AddressPurpose::RECEIVE};
-    if (!m_wallet->getAddress(destination, nullptr, nullptr, &purpose)) {
+    if (!m_wallet->getAddress(destination, nullptr, &purpose)) {
         return false;
     }
@@
-        if (wallet_address.purpose != wallet::AddressPurpose::RECEIVE || wallet_address.is_mine == wallet::ISMINE_NO) {
+        if (wallet_address.purpose != wallet::AddressPurpose::RECEIVE || !wallet_address.is_mine) {
             continue;
         }
```

## `aab195f74c` - `Merge bitcoin-core/gui-qml#551: Wallet close, settings, and mempool information`

Status:

- Patch application failed at first-parent position 294 after applying
  `fix-through-293-0b0eb9a7dc.patch`.
- The merge expands `OptionsQmlModel` with mempool settings, so the accumulated
  options-model hunk must be re-applied in the new file shape.
- Builds after applying `fix-through-293-0b0eb9a7dc.patch` while excluding
  `src/qml/models/options_model.cpp`, then applying the options patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-294-aab195f74c.patch`.

Failure:

- `SettingToInt` no longer exists in current Core settings helpers.
- The new `maxmempool` setting introduced by this merge also used
  `SettingToInt`.
- `DEFAULT_DESCENDANT_SIZE_LIMIT_KVB` was removed by current Core cluster-limit
  policy changes.

Fix sources:

- `275945b23e qml: adapt options model to Core v31 APIs` supplies the exact
  options model fix in the later branch.
- `b5f245f6f2 Remove unused DEFAULT_ANCESTOR_SIZE_LIMIT_KVB and
  DEFAULT_DESCENDANT_SIZE_LIMIT_KVB` removes the old descendant-size constant.
- Current `src/policy/policy.h` defines `DEFAULT_CLUSTER_SIZE_LIMIT_KVB`.

Patch to amend into `aab195f74c` after carrying the rest of
`fix-through-293-0b0eb9a7dc.patch`:

```diff
diff --git a/src/qml/models/options_model.cpp b/src/qml/models/options_model.cpp
index ec99b0470d..eae0d885cc 100644
--- a/src/qml/models/options_model.cpp
+++ b/src/qml/models/options_model.cpp
@@ -93,19 +93,19 @@ OptionsQmlModel::OptionsQmlModel(interfaces::Node& node, bool is_onboarded)
     : m_node{node}
     , m_onboarded{is_onboarded}
 {
-    m_dbcache_size_mib = SettingToInt(m_node.getPersistentSetting("dbcache"), DEFAULT_DB_CACHE >> 20);
+    m_dbcache_size_mib = SettingTo<int64_t>(m_node.getPersistentSetting("dbcache"), DEFAULT_DB_CACHE >> 20);

     m_listen = SettingToBool(m_node.getPersistentSetting("listen"), DEFAULT_LISTEN);

-    m_max_mempool_size_mb = SettingToInt(m_node.getPersistentSetting("maxmempool"), DEFAULT_MAX_MEMPOOL_SIZE_MB);
+    m_max_mempool_size_mb = SettingTo<int64_t>(m_node.getPersistentSetting("maxmempool"), DEFAULT_MAX_MEMPOOL_SIZE_MB);

     m_natpmp = SettingToBool(m_node.getPersistentSetting("natpmp"), DEFAULT_NATPMP);

-    int64_t prune_value{SettingToInt(m_node.getPersistentSetting("prune"), 0)};
+    int64_t prune_value{SettingTo<int64_t>(m_node.getPersistentSetting("prune"), 0)};
     m_prune = (prune_value > 1);
     m_prune_size_gb = m_prune ? PruneMiBtoGB(prune_value) : DEFAULT_PRUNE_TARGET_GB;

-    m_script_threads = SettingToInt(m_node.getPersistentSetting("par"), DEFAULT_SCRIPTCHECK_THREADS);
+    m_script_threads = SettingTo<int64_t>(m_node.getPersistentSetting("par"), DEFAULT_SCRIPTCHECK_THREADS);

     m_server = SettingToBool(m_node.getPersistentSetting("server"), false);
diff --git a/src/qml/models/options_model.h b/src/qml/models/options_model.h
index 402c436593..c783c46d91 100644
--- a/src/qml/models/options_model.h
+++ b/src/qml/models/options_model.h
@@ -161,7 +161,7 @@ private:
     bool m_listen;
     int m_max_mempool_size_mb;
     const int m_min_max_mempool_size_mb{
-        static_cast<int>((DEFAULT_DESCENDANT_SIZE_LIMIT_KVB * 1000 * 40 + 999999) / 1000000)
+        static_cast<int>((DEFAULT_CLUSTER_SIZE_LIMIT_KVB * 1000 * 40 + 999999) / 1000000)
     };
```

## `0b0eb9a7dc` - `Merge bitcoin-core/gui-qml#548: Apply password during onboarding and prompt for password when needed`

Status:

- Patch application failed at first-parent position 293 after applying
  `fix-through-291-fc227f1a86.patch`.
- The merge rewrites `WalletQmlModel` around `prepareTransactionInternal()` and
  passphrase/relock handling, so the accumulated wallet hunks must be applied
  in the new password-aware context.
- Builds after applying `fix-through-291-fc227f1a86.patch` while excluding
  `src/qml/models/walletqmlmodel.cpp`, then applying the wallet patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-293-0b0eb9a7dc.patch`.

Failure:

- The previous patch expected the display-unit wallet layout before passphrase
  preparation was introduced.
- The stale `createTransaction`, `getAddress`, transaction callback, and
  `fillPSBT` calls remain, but the successful send path now also needs to
  preserve `relock_guard.relock()` and transaction status handling.

Fix sources:

- Same API fix sources as `fc227f1a86`: `d7b35d9c7c`, `e426705a4d`,
  `dc4a5d1270`, and `f77b90485d`.
- `0b0eb9a7dc` introduces the password-aware `prepareTransactionInternal()`
  shape that must be preserved while adapting `CreatedTransactionResult`.

Patch to amend into `0b0eb9a7dc` after carrying the rest of
`fix-through-291-fc227f1a86.patch`:

```diff
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
index 4992932aef..1218967b41 100644
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@ -127,14 +127,12 @@ std::optional<CAmount> TryPreviewFee(interfaces::Wallet& wallet,
                                      const std::vector<wallet::CRecipient>& recipients,
                                      const wallet::CCoinControl& coin_control)
 {
-    int change_position{-1};
-    CAmount fee{0};
-    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, change_position, fee);
+    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, /*change_pos=*/std::nullopt);
     if (!result) {
         return std::nullopt;
     }

-    return fee;
+    return result->fee;
 }
@@ -552,7 +550,7 @@ QString WalletQmlModel::getAddressLabel(const QString& address) const
     }

     std::string label;
-    if (!m_wallet->getAddress(destination, &label, nullptr, nullptr)) {
+    if (!m_wallet->getAddress(destination, &label, nullptr)) {
         return {};
     }
@@ -564,7 +562,9 @@ std::unique_ptr<interfaces::Handler> WalletQmlModel::handleTransactionChanged(Tr
     if (!m_wallet) {
         return nullptr;
     }
-    return m_wallet->handleTransactionChanged(fn);
+    return m_wallet->handleTransactionChanged([fn = std::move(fn)](const Txid& txid, ChangeType status) {
+        fn(txid.ToUint256(), status);
+    });
 }
@@ -792,20 +792,18 @@ bool WalletQmlModel::prepareTransactionInternal(std::optional<SecureString> pass
         return false;
     }

-    int nChangePosRet = -1;
-    CAmount nFeeRequired = 0;
     const bool sign = !m_wallet->privateKeysDisabled();
-    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, sign, nChangePosRet, nFeeRequired);
+    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, sign, /*change_pos=*/std::nullopt);
     if (result) {
         if (m_current_transaction) {
             delete m_current_transaction;
         }
-        const CTransactionRef& newTx = *result;
+        const CTransactionRef& newTx = result->tx;
         m_current_transaction = new WalletQmlModelTransaction(m_send_recipients, this);
         m_current_transaction->setWtx(newTx);
-        m_current_transaction->setTransactionFee(nFeeRequired);
+        m_current_transaction->setTransactionFee(result->fee);
         if (subtract_fee_from_amount) {
-            m_current_transaction->reassignAmounts(nChangePosRet);
+            m_current_transaction->reassignAmounts(static_cast<int>(result->change_pos.value_or(-1)));
         }
         m_current_transaction->setDisplayUnit(m_display_unit);
         relock_guard.relock();
@@ -836,7 +834,7 @@ void WalletQmlModel::approveExternalSignerTransaction()
         PartiallySignedTransaction psbtx(mtx);
         bool complete = false;

-        const auto draft_err = m_wallet->fillPSBT(std::nullopt, /*sign=*/false, /*bip32derivs=*/true,
+        const auto draft_err = m_wallet->fillPSBT({.sign = false, .bip32_derivs = true},
             /*n_signed=*/nullptr, psbtx, complete);
@@ -846,7 +844,7 @@ void WalletQmlModel::approveExternalSignerTransaction()
             return;
         }

-        const auto sign_err = m_wallet->fillPSBT(std::nullopt, /*sign=*/true, /*bip32derivs=*/true,
+        const auto sign_err = m_wallet->fillPSBT({.sign = true, .bip32_derivs = true},
             /*n_signed=*/nullptr, psbtx, complete);
```

## `fc227f1a86` - `Merge bitcoin-core/gui-qml#536: Lang units settings`

Status:

- Patch application failed at first-parent position 291 after applying
  `fix-through-289-d273a836f4.patch`.
- The merge adjusts `WalletQmlModel` for display-unit settings, so the
  external-signer wallet hunks must be re-applied in the shifted file shape.
- Builds after applying `fix-through-289-d273a836f4.patch` while excluding
  `src/qml/models/walletqmlmodel.cpp`, then applying the wallet patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-291-fc227f1a86.patch`.

Failure:

- The previous patch expected the external-signer wallet layout before the
  display-unit changes.
- The same stale `createTransaction`, `getAddress`, transaction callback, and
  `fillPSBT` calls remain in the display-unit version of the file.

Fix sources:

- Same API fix sources as `d273a836f4`: `d7b35d9c7c`, `e426705a4d`,
  `dc4a5d1270`, and `f77b90485d`.
- `fc227f1a86` adds `m_current_transaction->setDisplayUnit(m_display_unit)`,
  which must be preserved while adapting the transaction creation result.

Patch to amend into `fc227f1a86` after carrying the rest of
`fix-through-289-d273a836f4.patch`:

```diff
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
index b89c5426bb..31cb2ecc49 100644
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@ -122,14 +122,12 @@ std::optional<CAmount> TryPreviewFee(interfaces::Wallet& wallet,
                                      const std::vector<wallet::CRecipient>& recipients,
                                      const wallet::CCoinControl& coin_control)
 {
-    int change_position{-1};
-    CAmount fee{0};
-    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, change_position, fee);
+    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, /*change_pos=*/std::nullopt);
     if (!result) {
         return std::nullopt;
     }

-    return fee;
+    return result->fee;
 }
@@ -496,7 +494,7 @@ QString WalletQmlModel::getAddressLabel(const QString& address) const
     }

     std::string label;
-    if (!m_wallet->getAddress(destination, &label, nullptr, nullptr)) {
+    if (!m_wallet->getAddress(destination, &label, nullptr)) {
         return {};
     }
@@ -508,7 +506,9 @@ std::unique_ptr<interfaces::Handler> WalletQmlModel::handleTransactionChanged(Tr
     if (!m_wallet) {
         return nullptr;
     }
-    return m_wallet->handleTransactionChanged(fn);
+    return m_wallet->handleTransactionChanged([fn = std::move(fn)](const Txid& txid, ChangeType status) {
+        fn(txid.ToUint256(), status);
+    });
 }
@@ -707,20 +707,18 @@ bool WalletQmlModel::prepareTransaction()
         return false;
     }

-    int nChangePosRet = -1;
-    CAmount nFeeRequired = 0;
     const bool sign = !m_wallet->privateKeysDisabled();
-    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, sign, nChangePosRet, nFeeRequired);
+    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, sign, /*change_pos=*/std::nullopt);
     if (result) {
         if (m_current_transaction) {
             delete m_current_transaction;
         }
-        const CTransactionRef& newTx = *result;
+        const CTransactionRef& newTx = result->tx;
         m_current_transaction = new WalletQmlModelTransaction(m_send_recipients, this);
         m_current_transaction->setWtx(newTx);
-        m_current_transaction->setTransactionFee(nFeeRequired);
+        m_current_transaction->setTransactionFee(result->fee);
         if (subtract_fee_from_amount) {
-            m_current_transaction->reassignAmounts(nChangePosRet);
+            m_current_transaction->reassignAmounts(static_cast<int>(result->change_pos.value_or(-1)));
         }
         m_current_transaction->setDisplayUnit(m_display_unit);
@@ -748,7 +746,7 @@ void WalletQmlModel::approveExternalSignerTransaction()
         PartiallySignedTransaction psbtx(mtx);
         bool complete = false;

-        const auto draft_err = m_wallet->fillPSBT(std::nullopt, /*sign=*/false, /*bip32derivs=*/true,
+        const auto draft_err = m_wallet->fillPSBT({.sign = false, .bip32_derivs = true},
             /*n_signed=*/nullptr, psbtx, complete);
@@ -758,7 +756,7 @@ void WalletQmlModel::approveExternalSignerTransaction()
             return;
         }

-        const auto sign_err = m_wallet->fillPSBT(std::nullopt, /*sign=*/true, /*bip32derivs=*/true,
+        const auto sign_err = m_wallet->fillPSBT({.sign = true, .bip32_derivs = true},
             /*n_signed=*/nullptr, psbtx, complete);
```

## `d273a836f4` - `Merge bitcoin-core/gui-qml#547: External signer wallet create and send`

Status:

- Patch application failed at first-parent position 289 after applying
  `fix-through-288-51bf51b72d.patch`.
- The merge rewrites `src/qml/models/walletqmlmodel.cpp` for external signer
  send review and approval, so the accumulated wallet hunks must be re-applied
  in the new file shape.
- The first adapted build also failed on the external-signer `fillPSBT` calls.
- Builds after applying `fix-through-288-51bf51b72d.patch` while excluding
  `src/qml/models/walletqmlmodel.cpp`, then applying the wallet patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-289-d273a836f4.patch`.

Failure:

- The previous wallet checkpoint expected the fee-selection wallet layout.
- The external-signer merge keeps the same stale `createTransaction`,
  `getAddress`, and transaction-changed callback APIs, but adds `sign` handling.
- The new external signer approval code also called the old positional
  `fillPSBT(std::nullopt, sign, bip32derivs, ...)` API.

Fix sources:

- `d7b35d9c7c qml: adapt wallet transaction creation API` supplies the
  `CreatedTransactionResult` updates while preserving the external signer
  `sign` variable.
- `e426705a4d qml: adapt wallet ownership and metadata APIs` supplies the
  `getAddress` and `handleTransactionChanged` updates.
- `dc4a5d1270 refactor: use PSBTFillOptions for filling and signing` changes
  the Core wallet interface.
- `f77b90485d qml: adapt remaining staging Core APIs` supplies the matching
  QML `PSBTFillOptions` call-site update.

Patch to amend into `d273a836f4` after carrying the rest of
`fix-through-288-51bf51b72d.patch`:

```diff
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
index 3740f04e48..cc26e33337 100644
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@ -122,14 +122,12 @@ std::optional<CAmount> TryPreviewFee(interfaces::Wallet& wallet,
                                      const std::vector<wallet::CRecipient>& recipients,
                                      const wallet::CCoinControl& coin_control)
 {
-    int change_position{-1};
-    CAmount fee{0};
-    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, change_position, fee);
+    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, /*change_pos=*/std::nullopt);
     if (!result) {
         return std::nullopt;
     }

-    return fee;
+    return result->fee;
 }
@@ -493,7 +491,7 @@ QString WalletQmlModel::getAddressLabel(const QString& address) const
     }

     std::string label;
-    if (!m_wallet->getAddress(destination, &label, nullptr, nullptr)) {
+    if (!m_wallet->getAddress(destination, &label, nullptr)) {
         return {};
     }
@@ -505,7 +503,9 @@ std::unique_ptr<interfaces::Handler> WalletQmlModel::handleTransactionChanged(Tr
     if (!m_wallet) {
         return nullptr;
     }
-    return m_wallet->handleTransactionChanged(fn);
+    return m_wallet->handleTransactionChanged([fn = std::move(fn)](const Txid& txid, ChangeType status) {
+        fn(txid.ToUint256(), status);
+    });
 }
@@ -704,20 +704,18 @@ bool WalletQmlModel::prepareTransaction()
         return false;
     }

-    int nChangePosRet = -1;
-    CAmount nFeeRequired = 0;
     const bool sign = !m_wallet->privateKeysDisabled();
-    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, sign, nChangePosRet, nFeeRequired);
+    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, sign, /*change_pos=*/std::nullopt);
     if (result) {
         if (m_current_transaction) {
             delete m_current_transaction;
         }
-        const CTransactionRef& newTx = *result;
+        const CTransactionRef& newTx = result->tx;
         m_current_transaction = new WalletQmlModelTransaction(m_send_recipients, this);
         m_current_transaction->setWtx(newTx);
-        m_current_transaction->setTransactionFee(nFeeRequired);
+        m_current_transaction->setTransactionFee(result->fee);
         if (subtract_fee_from_amount) {
-            m_current_transaction->reassignAmounts(nChangePosRet);
+            m_current_transaction->reassignAmounts(static_cast<int>(result->change_pos.value_or(-1)));
         }
         Q_EMIT currentTransactionChanged();
         return true;
@@ -744,7 +742,7 @@ void WalletQmlModel::approveExternalSignerTransaction()
         PartiallySignedTransaction psbtx(mtx);
         bool complete = false;

-        const auto draft_err = m_wallet->fillPSBT(std::nullopt, /*sign=*/false, /*bip32derivs=*/true,
+        const auto draft_err = m_wallet->fillPSBT({.sign = false, .bip32_derivs = true},
             /*n_signed=*/nullptr, psbtx, complete);
@@ -754,7 +752,7 @@ void WalletQmlModel::approveExternalSignerTransaction()
             return;
         }

-        const auto sign_err = m_wallet->fillPSBT(std::nullopt, /*sign=*/true, /*bip32derivs=*/true,
+        const auto sign_err = m_wallet->fillPSBT({.sign = true, .bip32_derivs = true},
             /*n_signed=*/nullptr, psbtx, complete);
```

## `51bf51b72d` - `Merge bitcoin-core/gui-qml#554: Implement Replace-By-Fee speed-up support in the wallet`

Status:

- Patch application failed at first-parent position 288 after applying
  `fix-through-287-5079ef3abe.patch`.
- The merge adds RBF metadata to `src/qml/models/transaction.cpp`, so the
  accumulated transaction ownership/hash hunks must be re-applied in the new
  file shape.
- Builds after applying `fix-through-287-5079ef3abe.patch` while excluding
  `src/qml/models/transaction.cpp`, then applying the transaction patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-288-51bf51b72d.patch`.

Failure:

- The old patch expected the pre-RBF transaction model around
  `Transaction::fromWalletTx()`.
- Current `interfaces::WalletTx` exposes `txin_is_mine` and `txout_is_mine` as
  bool vectors, not `wallet::isminetype`.
- Current transaction hashes are `Txid` and need `ToUint256()` for this model's
  existing `uint256` storage.

Fix sources:

- `e426705a4d qml: adapt wallet ownership and metadata APIs` supplies the same
  bool ownership and `Txid::ToUint256()` conversion.
- `51bf51b72d` introduces the RBF metadata fields, requiring the fix to be
  applied by context instead of carrying the earlier hunk verbatim.

Patch to amend into `51bf51b72d` after carrying the rest of
`fix-through-287-5079ef3abe.patch`:

```diff
diff --git a/src/qml/models/transaction.cpp b/src/qml/models/transaction.cpp
index a06b738789..e27a22e90f 100644
--- a/src/qml/models/transaction.cpp
+++ b/src/qml/models/transaction.cpp
@@ -10,10 +10,6 @@

 #include <QDateTime>

-using wallet::ISMINE_SPENDABLE;
-using wallet::ISMINE_NO;
-using wallet::isminetype;
-
 namespace {
     const int RecommendedNumConfirmations = 6;
 }
@@ -138,7 +134,7 @@ QList<QSharedPointer<Transaction>> Transaction::fromWalletTx(const interfaces::W
     CAmount nCredit = wtx.credit;
     CAmount nDebit = wtx.debit;
     CAmount nNet = nCredit - nDebit;
-    uint256 hash = wtx.tx->GetHash();
+    uint256 hash = wtx.tx->GetHash().ToUint256();
     QString txidStr = QString::fromStdString(hash.GetHex());
     std::map<std::string, std::string> mapValue = wtx.value_map;
@@ -152,14 +148,14 @@ QList<QSharedPointer<Transaction>> Transaction::fromWalletTx(const interfaces::W
     }

     bool involvesWatchAddress = false;
-    isminetype fAllFromMe = ISMINE_SPENDABLE;
+    bool fAllFromMe = true;
     bool any_from_me = false;
     if (wtx.is_coinbase) {
-        fAllFromMe = ISMINE_NO;
+        fAllFromMe = false;
     } else {
-        for (const isminetype mine : wtx.txin_is_mine)
+        for (const bool mine : wtx.txin_is_mine)
         {
-            if(fAllFromMe > mine) fAllFromMe = mine;
+            if (!mine) fAllFromMe = false;
             if (mine) any_from_me = true;
         }
     }
@@ -216,7 +212,7 @@ QList<QSharedPointer<Transaction>> Transaction::fromWalletTx(const interfaces::W
                 parts.append(sub);
             }

-            isminetype mine = wtx.txout_is_mine[i];
+            bool mine = wtx.txout_is_mine[i];
             if(mine)
             {
```

## `5079ef3abe` - `Merge bitcoin-core/gui-qml#546: Fee selection`

Status:

- Patch application failed at first-parent position 287 after applying
  `fix-through-280-931de054e6.patch`.
- The merge rewrites `src/qml/models/walletqmlmodel.cpp` for fee estimation and
  preview flows, so the accumulated wallet hunks must be re-applied in the new
  file shape.
- Builds after applying `fix-through-280-931de054e6.patch` while excluding
  `src/qml/models/walletqmlmodel.cpp`, then applying the wallet patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-287-5079ef3abe.patch`.

Failure:

- `TryPreviewFee()` and `prepareTransaction()` called the old
  `createTransaction(..., change_position, fee)` interface.
- `getAddressLabel()` still used the old four-argument `getAddress` call.
- `handleTransactionChanged()` still forwarded a callback expecting `uint256`,
  while current Core invokes handlers with `Txid`.

Fix sources:

- `d7b35d9c7c qml: adapt wallet transaction creation API` includes both
  fee-preview and send-preparation updates for the current
  `wallet::CreatedTransactionResult` return type.
- `e426705a4d qml: adapt wallet ownership and metadata APIs` supplies the
  `getAddress` and `handleTransactionChanged` updates.
- `5079ef3abe` introduces the fee-selection wallet model layout where these
  fixes must be applied by context.

Patch to amend into `5079ef3abe` after carrying the rest of
`fix-through-280-931de054e6.patch`:

```diff
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
index cc621bb24f..9725b582c8 100644
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@ -120,14 +120,12 @@ std::optional<CAmount> TryPreviewFee(interfaces::Wallet& wallet,
                                      const std::vector<wallet::CRecipient>& recipients,
                                      const wallet::CCoinControl& coin_control)
 {
-    int change_position{-1};
-    CAmount fee{0};
-    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, change_position, fee);
+    const auto result = wallet.createTransaction(recipients, coin_control, /*sign=*/false, /*change_pos=*/std::nullopt);
     if (!result) {
         return std::nullopt;
     }

-    return fee;
+    return result->fee;
 }
@@ -479,7 +477,7 @@ QString WalletQmlModel::getAddressLabel(const QString& address) const
     }

     std::string label;
-    if (!m_wallet->getAddress(destination, &label, nullptr, nullptr)) {
+    if (!m_wallet->getAddress(destination, &label, nullptr)) {
         return {};
     }
@@ -491,7 +489,9 @@ std::unique_ptr<interfaces::Handler> WalletQmlModel::handleTransactionChanged(Tr
     if (!m_wallet) {
         return nullptr;
     }
-    return m_wallet->handleTransactionChanged(fn);
+    return m_wallet->handleTransactionChanged([fn = std::move(fn)](const Txid& txid, ChangeType status) {
+        fn(txid.ToUint256(), status);
+    });
 }
@@ -682,19 +682,17 @@ bool WalletQmlModel::prepareTransaction()
         return false;
     }

-    int nChangePosRet = -1;
-    CAmount nFeeRequired = 0;
-    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, true, nChangePosRet, nFeeRequired);
+    const auto& result = m_wallet->createTransaction(*vec_send, coin_control, true, /*change_pos=*/std::nullopt);
     if (result) {
         if (m_current_transaction) {
             delete m_current_transaction;
         }
-        const CTransactionRef& newTx = *result;
+        const CTransactionRef& newTx = result->tx;
         m_current_transaction = new WalletQmlModelTransaction(m_send_recipients, this);
         m_current_transaction->setWtx(newTx);
-        m_current_transaction->setTransactionFee(nFeeRequired);
+        m_current_transaction->setTransactionFee(result->fee);
         if (subtract_fee_from_amount) {
-            m_current_transaction->reassignAmounts(nChangePosRet);
+            m_current_transaction->reassignAmounts(static_cast<int>(result->change_pos.value_or(-1)));
         }
         Q_EMIT currentTransactionChanged();
         return true;
```

## `931de054e6` - `Merge bitcoin-core/gui-qml#537: Add Wallet Import flow`

Status:

- Build failed at first-parent position 280 after applying
  `fix-through-278-13cd7f7e50.patch`.
- Builds after amending the wallet import restore call below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-280-931de054e6.patch`.

Failure:

- `WalletQmlController::startWalletImport()` called
  `WalletLoader::restoreWallet(backup_file, wallet_name, warnings)` with three
  arguments.
- Current `interfaces::WalletLoader::restoreWallet` requires a fourth
  `load_after_restore` argument.

Fix sources:

- `4ec2d18a07 wallet, interfaces, gui: Expose load_after_restore parameter`
  adds the current interface parameter.
- `f9dcad5b8b qml: pass load flag when restoring wallets` applies the QML-side
  fix and uses `/*load_after_restore=*/true` for the import flow.
- Current Qt wallet controller calls the same restore path with
  `/*load_after_restore=*/true` when the imported wallet should be loaded.

Patch to amend into `931de054e6`:

```diff
diff --git a/src/qml/walletqmlcontroller.cpp b/src/qml/walletqmlcontroller.cpp
--- a/src/qml/walletqmlcontroller.cpp
+++ b/src/qml/walletqmlcontroller.cpp
@@
         auto wallet = m_node.walletLoader().restoreWallet(
             fs::PathFromString(normalized_path.toStdString()),
             restore_wallet_name.toStdString(),
-            warning_messages);
+            warning_messages,
+            /*load_after_restore=*/true);
```

## `13cd7f7e50` - `Merge bitcoin-core/gui-qml#501: Wire RequestPayment page to PaymentRequest model`

Status:

- Patch application failed at first-parent position 278 after applying
  `fix-through-275-d355864640.patch`.
- The merge rewrites `src/qml/models/walletqmlmodel.cpp` for
  `PaymentRequest`, so the accumulated wallet hunks must be re-applied in the
  new file shape.
- Builds after applying `fix-through-275-d355864640.patch` while excluding
  `src/qml/models/walletqmlmodel.cpp`, then applying the wallet patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-278-13cd7f7e50.patch`.

Failure:

- The accumulated patch expected the older wallet model layout and failed at
  `src/qml/models/walletqmlmodel.cpp:21`.
- The same current-Core API fixes are still required in the new RequestPayment
  context:
  `getAddress` has three arguments, `handleTransactionChanged` passes `Txid`,
  and `createTransaction` returns `wallet::CreatedTransactionResult`.

Fix sources:

- `d7b35d9c7c qml: adapt send transaction creation to current wallet API`
  supplies the `createTransaction(..., std::nullopt)` and `res->tx` /
  `res->fee` update.
- `e426705a4d qml: adapt wallet ownership and metadata APIs` supplies the
  `getAddress` and `handleTransactionChanged` updates.
- `13cd7f7e50` introduces the new `PaymentRequest` wallet model layout that
  requires applying those fixes by context rather than by the older patch hunk.

Patch to amend into `13cd7f7e50` after carrying the rest of
`fix-through-275-d355864640.patch`:

```diff
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
index 62f8f89b36..3f6317bd6c 100644
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@ -233,7 +233,7 @@ QString WalletQmlModel::getAddressLabel(const QString& address) const
     }

     std::string label;
-    if (!m_wallet->getAddress(destination, &label, nullptr, nullptr)) {
+    if (!m_wallet->getAddress(destination, &label, nullptr)) {
         return {};
     }

@@ -245,7 +245,9 @@ std::unique_ptr<interfaces::Handler> WalletQmlModel::handleTransactionChanged(Tr
     if (!m_wallet) {
         return nullptr;
     }
-    return m_wallet->handleTransactionChanged(fn);
+    return m_wallet->handleTransactionChanged([fn = std::move(fn)](const Txid& txid, ChangeType status) {
+        fn(txid.ToUint256(), status);
+    });
 }

 bool WalletQmlModel::prepareTransaction()
@@ -269,17 +271,15 @@ bool WalletQmlModel::prepareTransaction()
         return false;
     }

-    int nChangePosRet = -1;
-    CAmount nFeeRequired = 0;
-    const auto& res = m_wallet->createTransaction(vecSend, m_coin_control, true, nChangePosRet, nFeeRequired);
+    const auto& res = m_wallet->createTransaction(vecSend, m_coin_control, true, /*change_pos=*/std::nullopt);
     if (res) {
         if (m_current_transaction) {
             delete m_current_transaction;
         }
-        CTransactionRef newTx = *res;
+        CTransactionRef newTx = res->tx;
         m_current_transaction = new WalletQmlModelTransaction(m_send_recipients, this);
         m_current_transaction->setWtx(newTx);
-        m_current_transaction->setTransactionFee(nFeeRequired);
+        m_current_transaction->setTransactionFee(res->fee);
         Q_EMIT currentTransactionChanged();
         return true;
     } else {
```

## `d355864640` - `Merge bitcoin-core/gui-qml#502: Fetch label information from wallet for activity list items`

Status:

- Build failed at first-parent position 275 after applying
  `fix-through-273-9c37ad5fdd.patch`.
- Builds after amending the wallet address metadata API call below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-275-d355864640.patch`.

Failure:

- `WalletQmlModel::getAddressLabel()` called
  `interfaces::Wallet::getAddress(destination, &label, nullptr, nullptr)`.
- Current `interfaces::Wallet::getAddress` takes three arguments:
  destination, optional label pointer, and optional purpose pointer.

Fix sources:

- `e426705a4d qml: adapt wallet ownership and metadata APIs` applies the same
  wallet metadata API update later in the branch.
- Current `src/interfaces/wallet.h` declares
  `getAddress(const CTxDestination&, std::string*, wallet::AddressPurpose*)`.

Patch to amend into `d355864640`:

```diff
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@
     std::string label;
-    if (!m_wallet->getAddress(destination, &label, nullptr, nullptr)) {
+    if (!m_wallet->getAddress(destination, &label, nullptr)) {
         return {};
     }
```

## `9c37ad5fdd` - `Merge bitcoin-core/gui-qml#529: Functional tests for peer disconnect, ban and unban`

Status:

- Patch application failed at first-parent position 273 after applying
  `fix-through-271-fca4f671c4.patch`.
- The only rejected hunk was in `src/qml/models/banlistmodel.h`; this commit
  already carries the `<qt/bantablemodel.h>` include fix natively.
- Builds after applying `fix-through-271-fca4f671c4.patch` while excluding
  `src/qml/models/banlistmodel.h`.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-273-9c37ad5fdd.patch`.

Failure:

- The accumulated patch expected to replace the stale
  `<bitcoin/src/qt/bantablemodel.h>` include.
- At this merge boundary the same include replacement is already present in
  the branch, so the old patch hunk must be dropped rather than amended again.

Fix sources:

- `8d8e35aba2` records the earlier manual fix for the stale `BanListModel`
  include.
- `9c37ad5fdd` / PR #529 carries the same `BanListModel` include fix natively.

Reproduction:

```bash
git apply --exclude='src/qml/models/banlistmodel.h' \
  /tmp/gui-qml-staging-buildwalk-logs/fix-through-271-fca4f671c4.patch
```

## `fca4f671c4` - `Merge bitcoin-core/gui-qml#527: Decouple Peers Models from bitcoin/src/qt`

Status:

- Patch application failed at first-parent position 271 after applying
  `fix-through-269-8d8e35aba2.patch`.
- The merge removes `peertableqmlmodel.h`, so the old peer-table include fix
  must be dropped at this point.
- Builds after applying the checkpoint to all other files and applying the
  adapted peer utility/details patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-271-fca4f671c4.patch`.

Failure:

- `peerdetailsmodel.h` was rewritten to use `PeerStatsUtil`, so the previous
  peer stats fix no longer applied.
- Current Core stores peer times as `NodeClock::time_point` and some durations
  at nanosecond precision. `PeerStatsUtil` still expected second timestamps or
  microsecond durations.
- `BanListModel` still needed the local `qt/bantablemodel.h` include.

Fix sources:

- `fca4f671c4` introduces `PeerStatsUtil`, `PeerListModel`, and removes the
  old `PeerTableQmlModel`.
- Current Core peer stats API requires `presync_height`,
  `NodeClock::time_point`, and explicit duration casts.
- `19521b4711` / `7f7a2d16fb` are later small fixes in the same node/ban model
  area.

Patch to amend into `fca4f671c4` after carrying the rest of
`fix-through-269-8d8e35aba2.patch`:

```diff
diff --git a/src/qml/models/banlistmodel.h b/src/qml/models/banlistmodel.h
index d9c76b62f2..8326d132a8 100644
--- a/src/qml/models/banlistmodel.h
+++ b/src/qml/models/banlistmodel.h
@@ -5,7 +5,7 @@
 #ifndef BITCOIN_QML_MODELS_BANLISTMODEL_H
 #define BITCOIN_QML_MODELS_BANLISTMODEL_H

-#include <bitcoin/src/qt/bantablemodel.h>
+#include <qt/bantablemodel.h>

 #include <QAbstractListModel>
 #include <QList>
diff --git a/src/qml/models/peerdetailsmodel.h b/src/qml/models/peerdetailsmodel.h
index ca9664e55f..cff25e0741 100644
--- a/src/qml/models/peerdetailsmodel.h
+++ b/src/qml/models/peerdetailsmodel.h
@@ -51,19 +51,19 @@ public:
     QString services() const { return PeerStatsUtil::FormatServicesStr(m_combinedStats->nodeStateStats.their_services); }
     bool transactionRelay() const { return m_combinedStats->nodeStateStats.m_relay_txs; }
     bool addressRelay() const { return m_combinedStats->nodeStateStats.m_addr_relay_enabled; }
-    QString startingHeight() const { return QString::number(m_combinedStats->nodeStateStats.m_starting_height); }
+    QString startingHeight() const { return QString::number(m_combinedStats->nodeStateStats.presync_height); }
@@
-    QString connectionDuration() const { return PeerStatsUtil::FormatDurationStr(GetTime<std::chrono::seconds>() - m_combinedStats->nodeStats.m_connected); }
-    QString lastSend() const { return PeerStatsUtil::FormatDurationStr(GetTime<std::chrono::seconds>() - m_combinedStats->nodeStats.m_last_send); }
-    QString lastReceived() const { return PeerStatsUtil::FormatDurationStr(GetTime<std::chrono::seconds>() - m_combinedStats->nodeStats.m_last_recv); }
+    QString connectionDuration() const { return PeerStatsUtil::FormatDurationStr(std::chrono::duration_cast<std::chrono::seconds>(NodeClock::now() - m_combinedStats->nodeStats.m_connected)); }
+    QString lastSend() const { return PeerStatsUtil::FormatDurationStr(std::chrono::duration_cast<std::chrono::seconds>(NodeClock::now() - m_combinedStats->nodeStats.m_last_send)); }
+    QString lastReceived() const { return PeerStatsUtil::FormatDurationStr(std::chrono::duration_cast<std::chrono::seconds>(NodeClock::now() - m_combinedStats->nodeStats.m_last_recv)); }
@@
-    QString pingTime() const { return PeerStatsUtil::FormatPingTime(m_combinedStats->nodeStats.m_last_ping_time); }
-    QString pingMin() const { return PeerStatsUtil::FormatPingTime(m_combinedStats->nodeStats.m_min_ping_time); }
-    QString pingWait() const { return PeerStatsUtil::FormatPingTime(m_combinedStats->nodeStateStats.m_ping_wait); }
-    QString timeOffset() const { return PeerStatsUtil::FormatTimeOffset(Ticks<std::chrono::seconds>(m_combinedStats->nodeStateStats.time_offset)); }
+    QString pingTime() const { return PeerStatsUtil::FormatPingTime(std::chrono::duration_cast<std::chrono::microseconds>(m_combinedStats->nodeStats.m_last_ping_time)); }
+    QString pingMin() const { return PeerStatsUtil::FormatPingTime(std::chrono::duration_cast<std::chrono::microseconds>(m_combinedStats->nodeStats.m_min_ping_time)); }
+    QString pingWait() const { return PeerStatsUtil::FormatPingTime(std::chrono::duration_cast<std::chrono::microseconds>(m_combinedStats->nodeStateStats.m_ping_wait)); }
+    QString timeOffset() const { return PeerStatsUtil::FormatTimeOffset(m_combinedStats->nodeStateStats.time_offset.count()); }
diff --git a/src/qml/models/peerlistmodel.cpp b/src/qml/models/peerlistmodel.cpp
index 390bb2d956..de2b9519c1 100644
--- a/src/qml/models/peerlistmodel.cpp
+++ b/src/qml/models/peerlistmodel.cpp
@@ -65,7 +65,7 @@ QVariant PeerListModel::data(const QModelIndex& index, int role) const
     case Network:
         return PeerStatsUtil::NetworkToQString(rec.nodeStats.m_network);
     case Ping:
-        return PeerStatsUtil::FormatPingTime(rec.nodeStats.m_min_ping_time);
+        return PeerStatsUtil::FormatPingTime(std::chrono::duration_cast<std::chrono::microseconds>(rec.nodeStats.m_min_ping_time));
diff --git a/src/qml/peerstatsutil.cpp b/src/qml/peerstatsutil.cpp
index 67b14ec7a8..1b0f818242 100644
--- a/src/qml/peerstatsutil.cpp
+++ b/src/qml/peerstatsutil.cpp
@@ -77,6 +77,15 @@ QString FormatPeerAge(std::chrono::seconds time_connected)
     return QObject::tr("%1 s").arg(age / 1s);
 }

+QString FormatPeerAge(NodeClock::time_point time_connected)
+{
+    const auto age{std::chrono::duration_cast<std::chrono::seconds>(NodeClock::now() - time_connected)};
+    if (age >= 24h) return QObject::tr("%1 d").arg(age / 24h);
+    if (age >= 1h) return QObject::tr("%1 h").arg(age / 1h);
+    if (age >= 1min) return QObject::tr("%1 m").arg(age / 1min);
+    return QObject::tr("%1 s").arg(age / 1s);
+}
+
 QString FormatServicesStr(quint64 mask)
 {
diff --git a/src/qml/peerstatsutil.h b/src/qml/peerstatsutil.h
index adeabc494b..cf08585e9d 100644
--- a/src/qml/peerstatsutil.h
+++ b/src/qml/peerstatsutil.h
@@ -6,6 +6,7 @@
 #define BITCOIN_QML_PEERSTATSUTIL_H

 #include <net.h>
+#include <util/time.h>
@@
 QString FormatDurationStr(std::chrono::seconds dur);
 QString FormatPeerAge(std::chrono::seconds time_connected);
+QString FormatPeerAge(NodeClock::time_point time_connected);
```

## `8d8e35aba2` - `Merge bitcoin-core/gui-qml#504: Add peer disconnect, ban and unban.`

Status:

- Failed to build at first-parent position 269 after applying
  `fix-through-263-ca598c4915.patch`.
- Builds after the include-path patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-269-8d8e35aba2.patch`.

Failure:

- `src/qml/models/banlistmodel.h` included
  `<bitcoin/src/qt/bantablemodel.h>`, which does not exist in the staging tree
  layout.

Fix sources:

- The local current header is `src/qt/bantablemodel.h`.
- Later cleanup commits `19521b4711` / `7f7a2d16fb` touch the new ban/node
  model area; the include-path fix follows the same source-root rule recorded
  for `ca598c4915`.

Patch to amend into `8d8e35aba2`:

```diff
diff --git a/src/qml/models/banlistmodel.h b/src/qml/models/banlistmodel.h
index d9c76b62f2..8326d132a8 100644
--- a/src/qml/models/banlistmodel.h
+++ b/src/qml/models/banlistmodel.h
@@ -5,7 +5,7 @@
 #ifndef BITCOIN_QML_MODELS_BANLISTMODEL_H
 #define BITCOIN_QML_MODELS_BANLISTMODEL_H

-#include <bitcoin/src/qt/bantablemodel.h>
+#include <qt/bantablemodel.h>

 #include <QAbstractListModel>
 #include <QList>
```

## `ca598c4915` - `Merge bitcoin-core/gui-qml#486: Add PeerTableQmlModel`

Status:

- Failed to build at first-parent position 263 after applying
  `fix-through-255-0ac8e6f137.patch`.
- Builds after the include-path patch below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-263-ca598c4915.patch`.

Failure:

- `src/qml/models/peertableqmlmodel.h` included
  `<bitcoin/src/qt/peertablemodel.h>`, which was valid for the temporary
  submodule layout but not for this staging tree where Bitcoin Core sources are
  rooted at `src/`.

Fix sources:

- The local current header is `src/qt/peertablemodel.h`.
- Later cleanup commits `989211a225` / `86fce1525c` remove remaining stale peer
  table include usage and confirm that QML code should no longer include via
  `bitcoin/src/...`.

Patch to amend into `ca598c4915`:

```diff
diff --git a/src/qml/models/peertableqmlmodel.h b/src/qml/models/peertableqmlmodel.h
index 01a9b95357..b77a753749 100644
--- a/src/qml/models/peertableqmlmodel.h
+++ b/src/qml/models/peertableqmlmodel.h
@@ -5,7 +5,7 @@
 #ifndef BITCOIN_QML_MODELS_PEERTABLEQMLMODEL_H
 #define BITCOIN_QML_MODELS_PEERTABLEQMLMODEL_H

-#include <bitcoin/src/qt/peertablemodel.h>
+#include <qt/peertablemodel.h>

 #include <QObject>
```

## `0ac8e6f137` - `Merge bitcoin-core/gui-qml#475: Add cmake, qt6, and bitcoin core submodule`

Status:

- Patch application failed at first-parent position 255 across many files.
- Building the raw sync commit showed many previous compatibility fixes were
  already present, so the correct action is to replace the accumulated patch
  with the reduced patch below.
- Builds after applying this reduced patch.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-255-0ac8e6f137.patch`.

Failure:

- `bitcoinqml` only compiled `bitcoin.cpp`, so linking failed once
  `bitcoin.cpp` referenced the QML model/control types and resources.
- `ThreadSafeMessageBox` no longer passes a caption and the old
  `LogPrintf()` helper is not available in this context.
- `btcsignals::connection` was only forward-declared because the file still
  included Boost signals instead of `btcsignals.h`.
- `chainmodel.h` included Core headers and initialized `Params()` in a header,
  which caused Qt moc to fail.
- Peer stats were partially current but still used the old
  `m_starting_height` field and old duration arithmetic.
- The activity/send wallet code still needed the current `Txid`,
  ownership-vector, `CreatedTransactionResult`, and `SettingTo<int64_t>`
  adaptations after the source glob caused all model files to compile.

Fix sources:

- `a64844ecc7 cmake: Build QML sources from src/qml` and `3c14dd1356 cmake:
  Embed QML resources` for the source glob and `bitcoin_qml.qrc`.
- `25a52764ca qml: adapt UI callbacks to Core v31`
  (`Rebased-From: 36c63267051f96cc7511e0d9488593824b3390ac`) for
  `ThreadSafeMessageBox`, `LogInfo`, and `btcsignals`.
- `8bfdea5801 qml: keep Core headers out of chain model moc`
  (`Rebased-From: 8200d44baed31f3b2f0a7b5125ffdc7c4bec9749`) for the
  `ChainModel` moc fix.
- `961619083f qml: Add PeerDetails page` plus current Core peer stats for
  `presync_height` and `NodeClock::now()` duration arithmetic.
- `e426705a4d qml: adapt wallet ownership and metadata APIs` for wallet
  ownership booleans and `Txid`/`uint256` bridging.
- `d7b35d9c7c qml: adapt wallet transaction creation API` for
  `CreatedTransactionResult`.
- `fa5672dcaf refactor: [gui] Use SettingTo<int64_t> over deprecated
  SettingToInt` for settings conversion.

Patch to amend into `0ac8e6f137`:

```diff
diff --git a/src/qml/CMakeLists.txt b/src/qml/CMakeLists.txt
index 727ca78a32..1d23ecfb0b 100644
--- a/src/qml/CMakeLists.txt
+++ b/src/qml/CMakeLists.txt
@@ -4,15 +4,32 @@

 set(CMAKE_AUTOMOC ON)

-add_library(bitcoinqml STATIC
-  bitcoin.cpp
+option(ENABLE_TEST_AUTOMATION "Enable test automation bridge for QML UI testing" OFF)
+
+set(QML_QRC "${CMAKE_CURRENT_SOURCE_DIR}/bitcoin_qml.qrc")
+qt6_add_resources(QML_QRC_CPP ${QML_QRC})
+
+file(GLOB_RECURSE QML_SOURCES
+  "${CMAKE_CURRENT_SOURCE_DIR}/*.cpp"
+  "${CMAKE_CURRENT_SOURCE_DIR}/*.h"
 )
+list(FILTER QML_SOURCES EXCLUDE REGEX "/main\\.cpp$")
+list(FILTER QML_SOURCES EXCLUDE REGEX "/androidnotifier\\.(cpp|h)$")
+if(NOT ENABLE_TEST_AUTOMATION)
+  list(FILTER QML_SOURCES EXCLUDE REGEX "/test/")
+endif()
+list(APPEND QML_SOURCES ${QML_QRC_CPP})
+
+add_library(bitcoinqml STATIC ${QML_SOURCES})
@@
 target_compile_definitions(bitcoinqml
   PUBLIC
     QT_NO_KEYWORDS
     QT_USE_QSTRINGBUILDER
 )
+if(ENABLE_TEST_AUTOMATION)
+  target_compile_definitions(bitcoinqml PUBLIC ENABLE_TEST_AUTOMATION)
+endif()
@@
 target_link_libraries(bitcoinqml
   PUBLIC
     core_interface
     bitcoin_node
+    univalue
+    Boost::headers
+    $<TARGET_NAME_IF_EXISTS:QRencode::QRencode>
     Qt6::Qml
-    Qt6::Widgets
     Qt6::Quick
+    Qt6::QuickControls2
+    Qt6::Network
+    Qt6::Widgets
 )
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
index 513e3c8b07..4f5ac1dad0 100644
--- a/src/qml/bitcoin.cpp
+++ b/src/qml/bitcoin.cpp
@@ -49,7 +49,7 @@
 #include <util/threadnames.h>
 #include <util/translation.h>

-#include <boost/signals2/connection.hpp>
+#include <btcsignals.h>
 #include <cassert>
 #include <memory>
 #include <tuple>
@@ -112,7 +112,6 @@ AppMode SetupAppMode()

 bool InitErrorMessageBox(
     const bilingual_str& message,
-    [[maybe_unused]] const std::string& caption,
     [[maybe_unused]] unsigned int style)
@@ -136,7 +135,7 @@ void DebugMessageHandler(QtMsgType type, const QMessageLogContext& context, cons
     if (type == QtDebugMsg) {
         LogDebug(BCLog::QT, "GUI: %s\n", msg.toStdString());
     } else {
-        LogPrintf("GUI: %s\n", msg.toStdString());
+        LogInfo("GUI: %s\n", msg.toStdString());
     }
 }
diff --git a/src/qml/models/chainmodel.cpp b/src/qml/models/chainmodel.cpp
index ce3a6b12ae..a09fc72cbd 100644
--- a/src/qml/models/chainmodel.cpp
+++ b/src/qml/models/chainmodel.cpp
@@ -4,16 +4,20 @@

 #include <qml/models/chainmodel.h>

+#include <chainparams.h>
+#include <interfaces/chain.h>
+
 #include <QDateTime>
 #include <QString>
 #include <QThread>
 #include <QTime>
-#include <interfaces/chain.h>
@@
 ChainModel::ChainModel(interfaces::Chain& chain)
-    : m_chain{chain}
+    : m_assumed_blockchain_size{Params().AssumedBlockchainSize()}
+    , m_assumed_chainstate_size{Params().AssumedChainStateSize()}
+    , m_chain{chain}
 {
diff --git a/src/qml/models/chainmodel.h b/src/qml/models/chainmodel.h
index 9318510eda..b0456bb03b 100644
--- a/src/qml/models/chainmodel.h
+++ b/src/qml/models/chainmodel.h
@@ -5,9 +5,6 @@
 #ifndef BITCOIN_QML_MODELS_CHAINMODEL_H
 #define BITCOIN_QML_MODELS_CHAINMODEL_H

-#include <chainparams.h>
-#include <interfaces/chain.h>
-
 #include <QObject>
@@
 private:
     QString m_current_network_name;
-    quint64 m_assumed_blockchain_size{ Params().AssumedBlockchainSize() };
-    quint64 m_assumed_chainstate_size{ Params().AssumedChainStateSize() };
+    quint64 m_assumed_blockchain_size;
+    quint64 m_assumed_chainstate_size;
diff --git a/src/qml/models/options_model.cpp b/src/qml/models/options_model.cpp
index fe850eb30b..2cdd7b1e62 100644
--- a/src/qml/models/options_model.cpp
+++ b/src/qml/models/options_model.cpp
@@ -30,17 +30,17 @@ OptionsQmlModel::OptionsQmlModel(interfaces::Node& node, bool is_onboarded)
     : m_node{node}
     , m_onboarded{is_onboarded}
 {
-    m_dbcache_size_mib = SettingToInt(m_node.getPersistentSetting("dbcache"), DEFAULT_DB_CACHE >> 20);
+    m_dbcache_size_mib = SettingTo<int64_t>(m_node.getPersistentSetting("dbcache"), DEFAULT_DB_CACHE >> 20);
@@
-    int64_t prune_value{SettingToInt(m_node.getPersistentSetting("prune"), 0)};
+    int64_t prune_value{SettingTo<int64_t>(m_node.getPersistentSetting("prune"), 0)};
@@
-    m_script_threads = SettingToInt(m_node.getPersistentSetting("par"), DEFAULT_SCRIPTCHECK_THREADS);
+    m_script_threads = SettingTo<int64_t>(m_node.getPersistentSetting("par"), DEFAULT_SCRIPTCHECK_THREADS);
diff --git a/src/qml/models/peerdetailsmodel.h b/src/qml/models/peerdetailsmodel.h
index 3b0211c119..2f933d292a 100644
--- a/src/qml/models/peerdetailsmodel.h
+++ b/src/qml/models/peerdetailsmodel.h
@@ -52,13 +52,13 @@ public:
     QString services() const { return GUIUtil::formatServicesStr(m_combinedStats->nodeStateStats.their_services); }
     bool transactionRelay() const { return m_combinedStats->nodeStateStats.m_relay_txs; }
     bool addressRelay() const { return m_combinedStats->nodeStateStats.m_addr_relay_enabled; }
-    QString startingHeight() const { return QString::number(m_combinedStats->nodeStateStats.m_starting_height); }
+    QString startingHeight() const { return QString::number(m_combinedStats->nodeStateStats.presync_height); }
@@
-    QString connectionDuration() const { return GUIUtil::formatDurationStr(GetTime<std::chrono::seconds>() - m_combinedStats->nodeStats.m_connected); }
-    QString lastSend() const { return GUIUtil::formatDurationStr(GetTime<std::chrono::seconds>() - m_combinedStats->nodeStats.m_last_send); }
-    QString lastReceived() const { return GUIUtil::formatDurationStr(GetTime<std::chrono::seconds>() - m_combinedStats->nodeStats.m_last_recv); }
+    QString connectionDuration() const { return GUIUtil::formatDurationStr(NodeClock::now() - m_combinedStats->nodeStats.m_connected); }
+    QString lastSend() const { return GUIUtil::formatDurationStr(NodeClock::now() - m_combinedStats->nodeStats.m_last_send); }
+    QString lastReceived() const { return GUIUtil::formatDurationStr(NodeClock::now() - m_combinedStats->nodeStats.m_last_recv); }
diff --git a/src/qml/models/transaction.cpp b/src/qml/models/transaction.cpp
index f9a6de3523..dc1cbd7545 100644
--- a/src/qml/models/transaction.cpp
+++ b/src/qml/models/transaction.cpp
@@ -10,10 +10,6 @@

 #include <QDateTime>

-using wallet::ISMINE_SPENDABLE;
-using wallet::ISMINE_NO;
-using wallet::isminetype;
-
 namespace {
@@
-    uint256 hash = wtx.tx->GetHash();
+    uint256 hash = wtx.tx->GetHash().ToUint256();
@@
-    isminetype fAllFromMe = ISMINE_SPENDABLE;
+    bool fAllFromMe = true;
@@
-        fAllFromMe = ISMINE_NO;
+        fAllFromMe = false;
@@
-        for (const isminetype mine : wtx.txin_is_mine)
+        for (const bool mine : wtx.txin_is_mine)
         {
-            if(fAllFromMe > mine) fAllFromMe = mine;
+            if (!mine) fAllFromMe = false;
@@
-            isminetype mine = wtx.txout_is_mine[i];
+            bool mine = wtx.txout_is_mine[i];
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
index abba0a4ef6..651c9a8d9d 100644
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@ -18,6 +18,8 @@
 #include <wallet/coincontrol.h>
 #include <wallet/wallet.h>

+#include <optional>
+
 #include <QTimer>
@@
-    return m_wallet->handleTransactionChanged(fn);
+    return m_wallet->handleTransactionChanged([fn = std::move(fn)](const Txid& txid, ChangeType status) {
+        fn(txid.ToUint256(), status);
+    });
@@
-    int nChangePosRet = -1;
-    CAmount nFeeRequired = 0;
-    const auto& res = m_wallet->createTransaction(vecSend, m_coin_control, true, nChangePosRet, nFeeRequired);
+    const auto& res = m_wallet->createTransaction(vecSend, m_coin_control, true, /*change_pos=*/std::nullopt);
@@
-        CTransactionRef newTx = *res;
+        CTransactionRef newTx = res->tx;
@@
-        m_current_transaction->setTransactionFee(nFeeRequired);
+        m_current_transaction->setTransactionFee(res->fee);
```

## `682b108b0d` - `Merge bitcoin-core/gui-qml#450: Add Multiple Recipients option to the Send form`

Status:

- Patch application failed at first-parent position 254 before the build:
  `fix-through-237-b1784ef595.patch` no longer applied to
  `src/qml/bitcoinamount.cpp` or `src/qml/models/walletqmlmodel.cpp`.
- Builds after applying `fix-through-237-b1784ef595.patch` to all other files
  and manually applying the adapted hunks below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-254-682b108b0d.patch`.

Failure:

- The multiple-recipient send loop reintroduced the old `CScript`-based
  `wallet::CRecipient` construction and old `createTransaction()` out-parameter
  API in a new context.
- `BitcoinAmount` was rewritten in this merge and still used `QRegExp`, which is
  removed in Qt 6.
- The existing `Txid`/`uint256` wallet lookup and transaction-change callback
  bridge also had to be re-applied in the rewritten `WalletQmlModel`.

Fix sources:

- `b96f87a6ca Merge bitcoin-core/gui-qml#435` for the introduced
  `BitcoinAmount` file; the required current-base fix is the Qt 6
  `QRegularExpression` replacement.
- `d7b35d9c7c qml: adapt wallet transaction creation API`
  (`Rebased-From: 5c790b7595f4c3271cee9d7eae944c276ad32ac0`) for the
  `CreatedTransactionResult` API.
- `e426705a4d qml: adapt wallet ownership and metadata APIs`
  (`Rebased-From: 836ffb876427e39a8bad04bcc2b1f643366244b2`) for the
  `Txid`/`uint256` bridge.

Reproduction:

1. Apply `/tmp/gui-qml-staging-buildwalk-logs/fix-through-237-b1784ef595.patch`
   to `682b108b0d`, excluding `src/qml/bitcoinamount.cpp` and
   `src/qml/models/walletqmlmodel.cpp`.
2. Apply this adapted patch to those two files.

```diff
diff --git a/src/qml/bitcoinamount.cpp b/src/qml/bitcoinamount.cpp
index 3cc31605d8..590e6b750c 100644
--- a/src/qml/bitcoinamount.cpp
+++ b/src/qml/bitcoinamount.cpp
@@ -4,7 +4,7 @@

 #include <qml/bitcoinamount.h>

-#include <QRegExp>
+#include <QRegularExpression>
 #include <QStringList>

 BitcoinAmount::BitcoinAmount(QObject* parent)
@@ -17,7 +17,7 @@ QString BitcoinAmount::sanitize(const QString &text)
     QString result = text;

     // Remove any invalid characters
-    result.remove(QRegExp("[^0-9.]"));
+    result.remove(QRegularExpression("[^0-9.]"));

     // Ensure only one decimal point
     QStringList parts = result.split('.');
@@ -147,7 +147,7 @@ void BitcoinAmount::fromDisplay(const QString& text)
         newSat = btcToSats(sanitized);
     } else {
         QString digitsOnly = text;
-        digitsOnly.remove(QRegExp("[^0-9]"));
+        digitsOnly.remove(QRegularExpression("[^0-9]"));
         newSat = digitsOnly.trimmed().isEmpty() ? 0 : digitsOnly.toLongLong();
     }
     setSatoshi(newSat);
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
index f05b2b38bb..651c9a8d9d 100644
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@ -18,6 +18,8 @@
 #include <wallet/coincontrol.h>
 #include <wallet/wallet.h>

+#include <optional>
+
 #include <QTimer>

 WalletQmlModel::WalletQmlModel(std::unique_ptr<interfaces::Wallet> wallet, QObject *parent)
@@ -76,7 +78,7 @@ interfaces::WalletTx WalletQmlModel::getWalletTx(const uint256& hash) const
     if (!m_wallet) {
         return {};
     }
-    return m_wallet->getWalletTx(hash);
+    return m_wallet->getWalletTx(Txid::FromUint256(hash));
 }

 bool WalletQmlModel::tryGetTxStatus(const uint256& txid,
@@ -87,7 +89,7 @@ bool WalletQmlModel::tryGetTxStatus(const uint256& txid,
     if (!m_wallet) {
         return false;
     }
-    return m_wallet->tryGetTxStatus(txid, tx_status, num_blocks, block_time);
+    return m_wallet->tryGetTxStatus(Txid::FromUint256(txid), tx_status, num_blocks, block_time);
 }

 std::unique_ptr<interfaces::Handler> WalletQmlModel::handleTransactionChanged(TransactionChangedFn fn)
@@ -95,7 +97,9 @@ std::unique_ptr<interfaces::Handler> WalletQmlModel::handleTransactionChanged(Tr
     if (!m_wallet) {
         return nullptr;
     }
-    return m_wallet->handleTransactionChanged(fn);
+    return m_wallet->handleTransactionChanged([fn = std::move(fn)](const Txid& txid, ChangeType status) {
+        fn(txid.ToUint256(), status);
+    });
 }

 bool WalletQmlModel::prepareTransaction()
@@ -107,8 +111,8 @@ bool WalletQmlModel::prepareTransaction()
     std::vector<wallet::CRecipient> vecSend;
     CAmount total = 0;
     for (auto* recipient : m_send_recipients->recipients()) {
-        CScript scriptPubKey = GetScriptForDestination(DecodeDestination(recipient->address().toStdString()));
-        wallet::CRecipient c_recipient = {scriptPubKey, recipient->cAmount(), recipient->subtractFeeFromAmount()};
+        CTxDestination destination = DecodeDestination(recipient->address().toStdString());
+        wallet::CRecipient c_recipient = {destination, recipient->cAmount(), recipient->subtractFeeFromAmount()};
         m_coin_control.m_feerate = CFeeRate(1000);
         vecSend.push_back(c_recipient);
         total += recipient->cAmount();
@@ -119,17 +123,15 @@ bool WalletQmlModel::prepareTransaction()
         return false;
     }

-    int nChangePosRet = -1;
-    CAmount nFeeRequired = 0;
-    const auto& res = m_wallet->createTransaction(vecSend, m_coin_control, true, nChangePosRet, nFeeRequired);
+    const auto& res = m_wallet->createTransaction(vecSend, m_coin_control, true, /*change_pos=*/std::nullopt);
     if (res) {
         if (m_current_transaction) {
             delete m_current_transaction;
         }
-        CTransactionRef newTx = *res;
+        CTransactionRef newTx = res->tx;
         m_current_transaction = new WalletQmlModelTransaction(m_send_recipients, this);
         m_current_transaction->setWtx(newTx);
-        m_current_transaction->setTransactionFee(nFeeRequired);
+        m_current_transaction->setTransactionFee(res->fee);
         Q_EMIT currentTransactionChanged();
         return true;
     } else {
```

## `b1784ef595` - `qml: Add CoinsListModel to WalletQmlModel`

Status:

- Patch application failed at first-parent position 237 before the build:
  `fix-through-232-aaf0072f1f.patch` no longer applied to
  `src/qml/models/walletqmlmodel.cpp`.
- Builds after applying `fix-through-232-aaf0072f1f.patch` to all other files
  and manually applying the adapted hunks below.
- Saved accumulated checkpoint:
  `/tmp/gui-qml-staging-buildwalk-logs/fix-through-237-b1784ef595.patch`.

Failure:

- This commit adds `CoinsListModel` to `WalletQmlModel`, changing nearby
  constructor/destructor and coin-control context enough that the accumulated
  `WalletQmlModel` patch no longer applies.
- No new Core API source was needed. This is a context split for the fixes
  already found at `139b798fdb` and `aaf0072f1f`.

Fix sources:

- `e426705a4d qml: adapt wallet ownership and metadata APIs`
  (`Rebased-From: 836ffb876427e39a8bad04bcc2b1f643366244b2`) for boolean
  wallet ownership and `Txid`/`uint256` bridging.
- `d7b35d9c7c qml: adapt wallet transaction creation API`
  (`Rebased-From: 5c790b7595f4c3271cee9d7eae944c276ad32ac0`) for
  `CreatedTransactionResult`.
- `b1784ef595` itself introduces the `m_coin_control` member, so the
  `createTransaction()` fix must use `m_coin_control` instead of the local
  `coinControl` from the previous commit.

Reproduction:

1. Apply `/tmp/gui-qml-staging-buildwalk-logs/fix-through-232-aaf0072f1f.patch`
   to `b1784ef595`, excluding `src/qml/models/walletqmlmodel.cpp` and
   `src/qml/models/transaction.cpp`.
2. Apply this adapted patch to those two files.

```diff
diff --git a/src/qml/models/transaction.cpp b/src/qml/models/transaction.cpp
index d50baa3a91..dc1cbd7545 100644
--- a/src/qml/models/transaction.cpp
+++ b/src/qml/models/transaction.cpp
@@ -10,11 +10,6 @@

 #include <QDateTime>

-using wallet::ISMINE_SPENDABLE;
-using wallet::ISMINE_NO;
-using wallet::ISMINE_WATCH_ONLY;
-using wallet::isminetype;
-
 namespace {
     const int RecommendedNumConfirmations = 6;
 }
@@ -139,29 +134,23 @@ QList<QSharedPointer<Transaction>> Transaction::fromWalletTx(const interfaces::W
     CAmount nCredit = wtx.credit;
     CAmount nDebit = wtx.debit;
     CAmount nNet = nCredit - nDebit;
-    uint256 hash = wtx.tx->GetHash();
+    uint256 hash = wtx.tx->GetHash().ToUint256();
     std::map<std::string, std::string> mapValue = wtx.value_map;

     bool involvesWatchAddress = false;
-    isminetype fAllFromMe = ISMINE_SPENDABLE;
+    bool fAllFromMe = true;
     bool any_from_me = false;
     if (wtx.is_coinbase) {
-        fAllFromMe = ISMINE_NO;
+        fAllFromMe = false;
     } else {
-        for (const isminetype mine : wtx.txin_is_mine)
+        for (const bool mine : wtx.txin_is_mine)
         {
-            if(mine & ISMINE_WATCH_ONLY) involvesWatchAddress = true;
-            if(fAllFromMe > mine) fAllFromMe = mine;
+            if (!mine) fAllFromMe = false;
             if (mine) any_from_me = true;
         }
     }

     if (fAllFromMe || !any_from_me) {
-        for (const isminetype mine : wtx.txout_is_mine)
-        {
-            if(mine & ISMINE_WATCH_ONLY) involvesWatchAddress = true;
-        }
-
         CAmount nTxFee = nDebit - wtx.tx->GetValueOut();


@@ -209,7 +198,7 @@ QList<QSharedPointer<Transaction>> Transaction::fromWalletTx(const interfaces::W
                 parts.append(sub);
             }

-            isminetype mine = wtx.txout_is_mine[i];
+            bool mine = wtx.txout_is_mine[i];
             if(mine)
             {
                 //
@@ -219,7 +208,7 @@ QList<QSharedPointer<Transaction>> Transaction::fromWalletTx(const interfaces::W
                 QSharedPointer<Transaction> sub = QSharedPointer<Transaction>::create(hash, nTime);
                 sub->idx = i; // vout index
                 sub->credit = txout.nValue;
-                sub->involvesWatchAddress = mine & ISMINE_WATCH_ONLY;
+                sub->involvesWatchAddress = false;
                 if (wtx.txout_address_is_mine[i])
                 {
                     // Received by Bitcoin Address
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
index 55df50c8da..bc5087106c 100644
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@ -15,6 +15,8 @@
 #include <wallet/coincontrol.h>
 #include <wallet/wallet.h>

+#include <optional>
+
 #include <QTimer>

 WalletQmlModel::WalletQmlModel(std::unique_ptr<interfaces::Wallet> wallet, QObject *parent)
@@ -73,7 +75,7 @@ interfaces::WalletTx WalletQmlModel::getWalletTx(const uint256& hash) const
     if (!m_wallet) {
         return {};
     }
-    return m_wallet->getWalletTx(hash);
+    return m_wallet->getWalletTx(Txid::FromUint256(hash));
 }

 bool WalletQmlModel::tryGetTxStatus(const uint256& txid,
@@ -84,7 +86,7 @@ bool WalletQmlModel::tryGetTxStatus(const uint256& txid,
     if (!m_wallet) {
         return false;
     }
-    return m_wallet->tryGetTxStatus(txid, tx_status, num_blocks, block_time);
+    return m_wallet->tryGetTxStatus(Txid::FromUint256(txid), tx_status, num_blocks, block_time);
 }

 std::unique_ptr<interfaces::Handler> WalletQmlModel::handleTransactionChanged(TransactionChangedFn fn)
@@ -92,7 +94,9 @@ std::unique_ptr<interfaces::Handler> WalletQmlModel::handleTransactionChanged(Tr
     if (!m_wallet) {
         return nullptr;
     }
-    return m_wallet->handleTransactionChanged(fn);
+    return m_wallet->handleTransactionChanged([fn = std::move(fn)](const Txid& txid, ChangeType status) {
+        fn(txid.ToUint256(), status);
+    });
 }

 bool WalletQmlModel::prepareTransaction()
@@ -101,8 +105,8 @@ bool WalletQmlModel::prepareTransaction()
         return false;
     }

-    CScript scriptPubKey = GetScriptForDestination(DecodeDestination(m_current_recipient->address().toStdString()));
-    wallet::CRecipient recipient = {scriptPubKey, m_current_recipient->cAmount(), m_current_recipient->subtractFeeFromAmount()};
+    CTxDestination destination = DecodeDestination(m_current_recipient->address().toStdString());
+    wallet::CRecipient recipient = {destination, m_current_recipient->cAmount(), m_current_recipient->subtractFeeFromAmount()};
     m_coin_control.m_feerate = CFeeRate(1000);

     CAmount balance = m_wallet->getBalance();
@@ -111,17 +115,15 @@ bool WalletQmlModel::prepareTransaction()
     }

     std::vector<wallet::CRecipient> vecSend{recipient};
-    int nChangePosRet = -1;
-    CAmount nFeeRequired = 0;
-    const auto& res = m_wallet->createTransaction(vecSend, m_coin_control, true, nChangePosRet, nFeeRequired);
+    const auto& res = m_wallet->createTransaction(vecSend, m_coin_control, true, /*change_pos=*/std::nullopt);
     if (res) {
         if (m_current_transaction) {
             delete m_current_transaction;
         }
-        CTransactionRef newTx = *res;
+        CTransactionRef newTx = res->tx;
         m_current_transaction = new WalletQmlModelTransaction(m_current_recipient, this);
         m_current_transaction->setWtx(newTx);
-        m_current_transaction->setTransactionFee(nFeeRequired);
+        m_current_transaction->setTransactionFee(res->fee);
         Q_EMIT currentTransactionChanged();
         return true;
     } else {
```

## `aaf0072f1f` - `Merge bitcoin-core/gui-qml#445: Introduce Send pages for singlesig, single input/output send`

Status:

- Failed to build at first-parent position 232 after applying
  `fix-through-231-139b798fdb.patch`.
- Builds after applying the incremental patch below and saving the accumulated
  checkpoint as `/tmp/gui-qml-staging-buildwalk-logs/fix-through-232-aaf0072f1f.patch`.

Failure:

- `wallet::CRecipient` now stores a `CTxDestination`; this commit still builds
  a `CScript` with `GetScriptForDestination()` and tries to initialize
  `CRecipient` from it.
- `interfaces::Wallet::createTransaction()` now takes four arguments and
  returns `util::Result<wallet::CreatedTransactionResult>` with `tx`, `fee`,
  and `change_pos` fields; this commit still passes the old out-parameters
  `nChangePosRet` and `nFeeRequired` and treats the result as a
  `CTransactionRef`.

Fix sources:

- `d7b35d9c7c qml: adapt wallet transaction creation API`
  (`Rebased-From: 5c790b7595f4c3271cee9d7eae944c276ad32ac0`) contains the
  later QML update to the new `createTransaction()` return type.
- Current `src/wallet/wallet.h` defines `wallet::CRecipient` with a
  `CTxDestination dest` field.
- Current `src/interfaces/wallet.h` defines
  `Wallet::createTransaction(..., std::optional<unsigned int> change_pos)`.

Patch to amend into `aaf0072f1f` after the `139b798fdb` fixes:

```diff
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
index 5842cc1d17..d151309f4c 100644
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@ -16,6 +16,8 @@
 #include <wallet/coincontrol.h>
 #include <wallet/wallet.h>

+#include <optional>
+
 #include <QTimer>

 WalletQmlModel::WalletQmlModel(std::unique_ptr<interfaces::Wallet> wallet, QObject *parent)
@@ -95,8 +97,8 @@ bool WalletQmlModel::prepareTransaction()
         return false;
     }

-    CScript scriptPubKey = GetScriptForDestination(DecodeDestination(m_current_recipient->address().toStdString()));
-    wallet::CRecipient recipient = {scriptPubKey, m_current_recipient->cAmount(), m_current_recipient->subtractFeeFromAmount()};
+    CTxDestination destination = DecodeDestination(m_current_recipient->address().toStdString());
+    wallet::CRecipient recipient = {destination, m_current_recipient->cAmount(), m_current_recipient->subtractFeeFromAmount()};
     wallet::CCoinControl coinControl;
     coinControl.m_feerate = CFeeRate(1000);

@@ -106,17 +108,15 @@ bool WalletQmlModel::prepareTransaction()
     }

     std::vector<wallet::CRecipient> vecSend{recipient};
-    int nChangePosRet = -1;
-    CAmount nFeeRequired = 0;
-    const auto& res = m_wallet->createTransaction(vecSend, coinControl, true, nChangePosRet, nFeeRequired);
+    const auto& res = m_wallet->createTransaction(vecSend, coinControl, true, /*change_pos=*/std::nullopt);
     if (res) {
         if (m_current_transaction) {
             delete m_current_transaction;
         }
-        CTransactionRef newTx = *res;
+        CTransactionRef newTx = res->tx;
         m_current_transaction = new WalletQmlModelTransaction(m_current_recipient, this);
         m_current_transaction->setWtx(newTx);
-        m_current_transaction->setTransactionFee(nFeeRequired);
+        m_current_transaction->setTransactionFee(res->fee);
         Q_EMIT currentTransactionChanged();
         return true;
     } else {
```

## `139b798fdb` - `Merge bitcoin-core/gui-qml#442: Introduce the Desktop Wallet Activity Page`

Status:

- Failed to build at first-parent position 231 after applying
  `fix-through-229-b96f87a6ca.patch`.
- Builds after applying the incremental patch below and saving the accumulated
  checkpoint as `/tmp/gui-qml-staging-buildwalk-logs/fix-through-231-139b798fdb.patch`.

Failure:

- `src/qml/models/transaction.cpp` imported removed wallet ownership names
  (`wallet::isminetype`, `wallet::ISMINE_*`).
- `interfaces::WalletTx` now stores transaction ownership metadata as
  `std::vector<bool>`, so the activity model can no longer inspect watch-only
  ownership flags there.
- `CTransaction::GetHash()` returns `Txid`, while the introduced QML
  transaction model stores `uint256`.
- `interfaces::Wallet::getWalletTx`, `tryGetTxStatus`, and
  `handleTransactionChanged` now use `Txid`, while this commit's QML activity
  model still passes `uint256`.

Fix sources:

- `e426705a4d qml: adapt wallet ownership and metadata APIs`
  (`Rebased-From: 836ffb876427e39a8bad04bcc2b1f643366244b2`) contains the
  later QML conversion from `isminetype` ownership metadata to booleans and the
  transaction-change callback bridge from `Txid` back to `uint256`.
- Current `src/interfaces/wallet.h` is the source for the `Txid` wallet lookup
  and callback signatures.
- Current `src/primitives/transaction_identifier.h` provides
  `Txid::FromUint256()` and `Txid::ToUint256()`.

Patch to amend into `139b798fdb`:

```diff
diff --git a/src/qml/models/transaction.cpp b/src/qml/models/transaction.cpp
index d50baa3a91..dc1cbd7545 100644
--- a/src/qml/models/transaction.cpp
+++ b/src/qml/models/transaction.cpp
@@ -10,11 +10,6 @@

 #include <QDateTime>

-using wallet::ISMINE_SPENDABLE;
-using wallet::ISMINE_NO;
-using wallet::ISMINE_WATCH_ONLY;
-using wallet::isminetype;
-
 namespace {
     const int RecommendedNumConfirmations = 6;
 }
@@ -139,29 +134,23 @@ QList<QSharedPointer<Transaction>> Transaction::fromWalletTx(const interfaces::W
     CAmount nCredit = wtx.credit;
     CAmount nDebit = wtx.debit;
     CAmount nNet = nCredit - nDebit;
-    uint256 hash = wtx.tx->GetHash();
+    uint256 hash = wtx.tx->GetHash().ToUint256();
     std::map<std::string, std::string> mapValue = wtx.value_map;

     bool involvesWatchAddress = false;
-    isminetype fAllFromMe = ISMINE_SPENDABLE;
+    bool fAllFromMe = true;
     bool any_from_me = false;
     if (wtx.is_coinbase) {
-        fAllFromMe = ISMINE_NO;
+        fAllFromMe = false;
     } else {
-        for (const isminetype mine : wtx.txin_is_mine)
+        for (const bool mine : wtx.txin_is_mine)
         {
-            if(mine & ISMINE_WATCH_ONLY) involvesWatchAddress = true;
-            if(fAllFromMe > mine) fAllFromMe = mine;
+            if (!mine) fAllFromMe = false;
             if (mine) any_from_me = true;
         }
     }

     if (fAllFromMe || !any_from_me) {
-        for (const isminetype mine : wtx.txout_is_mine)
-        {
-            if(mine & ISMINE_WATCH_ONLY) involvesWatchAddress = true;
-        }
-
         CAmount nTxFee = nDebit - wtx.tx->GetValueOut();


@@ -209,7 +198,7 @@ QList<QSharedPointer<Transaction>> Transaction::fromWalletTx(const interfaces::W
                 parts.append(sub);
             }

-            isminetype mine = wtx.txout_is_mine[i];
+            bool mine = wtx.txout_is_mine[i];
             if(mine)
             {
                 //
@@ -219,7 +208,7 @@ QList<QSharedPointer<Transaction>> Transaction::fromWalletTx(const interfaces::W
                 QSharedPointer<Transaction> sub = QSharedPointer<Transaction>::create(hash, nTime);
                 sub->idx = i; // vout index
                 sub->credit = txout.nValue;
-                sub->involvesWatchAddress = mine & ISMINE_WATCH_ONLY;
+                sub->involvesWatchAddress = false;
                 if (wtx.txout_address_is_mine[i])
                 {
                     // Received by Bitcoin Address
diff --git a/src/qml/models/walletqmlmodel.cpp b/src/qml/models/walletqmlmodel.cpp
index f0c6b45938..5842cc1d17 100644
--- a/src/qml/models/walletqmlmodel.cpp
+++ b/src/qml/models/walletqmlmodel.cpp
@@ -56,7 +56,7 @@ interfaces::WalletTx WalletQmlModel::getWalletTx(const uint256& hash) const
     if (!m_wallet) {
         return {};
     }
-    return m_wallet->getWalletTx(hash);
+    return m_wallet->getWalletTx(Txid::FromUint256(hash));
 }

 bool WalletQmlModel::tryGetTxStatus(const uint256& txid,
@@ -67,7 +67,7 @@ bool WalletQmlModel::tryGetTxStatus(const uint256& txid,
     if (!m_wallet) {
         return false;
     }
-    return m_wallet->tryGetTxStatus(txid, tx_status, num_blocks, block_time);
+    return m_wallet->tryGetTxStatus(Txid::FromUint256(txid), tx_status, num_blocks, block_time);
 }

 WalletQmlModel::~WalletQmlModel()
@@ -80,5 +80,7 @@ std::unique_ptr<interfaces::Handler> WalletQmlModel::handleTransactionChanged(Tr
     if (!m_wallet) {
         return nullptr;
     }
-    return m_wallet->handleTransactionChanged(fn);
+    return m_wallet->handleTransactionChanged([fn = std::move(fn)](const Txid& txid, ChangeType status) {
+        fn(txid.ToUint256(), status);
+    });
 }
```

## `b96f87a6ca` - `Merge bitcoin-core/gui-qml#435: Initial Template for Request Payment page`

Build status after fix: passed `bitcoin-qml` at first-parent position 229.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-229-b96f87a6ca.patch
```

Failure found:

- `src/qml/bitcoinamount.cpp` included and used Qt 5 `QRegExp`.
- Qt 6 does not provide `QRegExp`, so the file failed to compile.

Fix sources:

- Later branch state uses `QRegularExpression` in `BitcoinAmount`.
- Qt 6 replacement for this usage is `QRegularExpression`.

Patch hunk to amend into `b96f87a6ca`:

```diff
diff --git a/src/qml/bitcoinamount.cpp b/src/qml/bitcoinamount.cpp
@@
-#include <QRegExp>
+#include <QRegularExpression>
@@
-    result.remove(QRegExp("[^0-9.]"));
+    result.remove(QRegularExpression("[^0-9.]"));
```

## `d871a60ab7` - `Merge bitcoin-core/gui-qml#430: Allow IPv6 in Proxy settings and moving validation out from the UI into the model/ interface`

Build status after fix: passed `bitcoin-qml` at first-parent position 225.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-225-d871a60ab7.patch
```

Failure found:

- `NodeModel` called `interfaces::Node::validateProxyAddress()` and
  `interfaces::Node::defaultProxyAddress()`.
- Those interface methods are not present in the current Core base.

Fix sources:

- Later branch state implements proxy validation directly in `NodeModel`.
- Current `netbase.h` provides `SplitHostPort`, `LookupNumeric`, `CService`,
  and `Proxy`.
- Current QML branch uses `127.0.0.1:9050` as the default proxy address.

Patch hunks to amend into `d871a60ab7`:

```diff
diff --git a/src/qml/models/nodemodel.h b/src/qml/models/nodemodel.h
@@
 #include <QObject>
 #include <QString>

+const char DEFAULT_PROXY_HOST[] = "127.0.0.1";
+constexpr uint16_t DEFAULT_PROXY_PORT = 9050;
+
diff --git a/src/qml/models/nodemodel.cpp b/src/qml/models/nodemodel.cpp
@@
 #include <interfaces/node.h>
 #include <net.h>
+#include <netbase.h>
 #include <node/interface_ui.h>
+#include <util/string.h>
@@
 bool NodeModel::validateProxyAddress(QString address_port)
 {
-    return m_node.validateProxyAddress(address_port.toStdString());
+    uint16_t port{0};
+    std::string addr_port{address_port.toStdString()};
+    std::string hostname;
+    if (!SplitHostPort(addr_port, port, hostname) || !port) return false;
+
+    CService serv(LookupNumeric(addr_port, DEFAULT_PROXY_PORT));
+    Proxy addrProxy = Proxy(serv, true);
+    return addrProxy.IsValid();
 }

 QString NodeModel::defaultProxyAddress()
 {
-    return QString::fromStdString(m_node.defaultProxyAddress());
+    return QString::fromStdString(std::string(DEFAULT_PROXY_HOST) + ":" + util::ToString(DEFAULT_PROXY_PORT));
 }
```

## `4ddf0e9418` - `Merge bitcoin-core/gui-qml#417: Introduce WalletModel and loadWallet functionality`

Build status after fix: passed `bitcoin-qml` at first-parent position 224.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-224-4ddf0e9418.patch
```

Failure found:

- The accumulated patch still contained the temporary `WalletController` to
  `WalletQmlController` rename for `src/qml/walletcontroller.*`.
- This commit deletes `walletcontroller.*` and introduces
  `walletqmlcontroller.*`, so those temporary hunks must be dropped.
- `src/qml/bitcoin.cpp` also gained wallet-controller lifecycle wiring, which
  conflicted with the old single declaration location.

Fix sources:

- `4ddf0e9418` is the source of the real `WalletQmlController` replacement.
- The earlier `c01ca8682b` class rename is only needed before this commit.

Patch detail:

```text
git apply --3way \
  --exclude=src/qml/walletcontroller.cpp \
  --exclude=src/qml/walletcontroller.h \
  /tmp/gui-qml-staging-buildwalk-logs/fix-through-221-961619083f.patch
```

Conflict resolution:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-    WalletQmlController wallet_controller(*node);
-
     QQmlApplicationEngine engine;
```

## `961619083f` - `qml: Add PeerDetails page`

Build status after fix: passed `bitcoin-qml` at first-parent position 221.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-221-961619083f.patch
```

Failures found:

- `CNodeStateStats::m_starting_height` no longer exists in current Core.
- `CNodeStats::m_connected`, `m_last_send`, and `m_last_recv` are now
  `NodeClock::time_point`, so subtracting them from
  `GetTime<std::chrono::seconds>()` fails.
- `CNodeStats::nTimeOffset` no longer exists; current Core exposes
  `CNodeStateStats::time_offset`.

Fix sources:

- Current `src/net_processing.h` exposes `presync_height` and `time_offset`.
- Current `src/net.h` exposes peer timestamps as `NodeClock::time_point`.
- Current Qt peer age formatting uses `NodeClock::now() - connected`.

Patch hunks to amend into `961619083f`:

```diff
diff --git a/src/qml/models/peerdetailsmodel.h b/src/qml/models/peerdetailsmodel.h
@@
-    QString startingHeight() const { return QString::number(m_combinedStats->nodeStateStats.m_starting_height); }
+    QString startingHeight() const { return QString::number(m_combinedStats->nodeStateStats.presync_height); }
@@
-    QString connectionDuration() const { return GUIUtil::formatDurationStr(GetTime<std::chrono::seconds>() - m_combinedStats->nodeStats.m_connected); }
-    QString lastSend() const { return GUIUtil::formatDurationStr(GetTime<std::chrono::seconds>() - m_combinedStats->nodeStats.m_last_send); }
-    QString lastReceived() const { return GUIUtil::formatDurationStr(GetTime<std::chrono::seconds>() - m_combinedStats->nodeStats.m_last_recv); }
+    QString connectionDuration() const { return GUIUtil::formatDurationStr(NodeClock::now() - m_combinedStats->nodeStats.m_connected); }
+    QString lastSend() const { return GUIUtil::formatDurationStr(NodeClock::now() - m_combinedStats->nodeStats.m_last_send); }
+    QString lastReceived() const { return GUIUtil::formatDurationStr(NodeClock::now() - m_combinedStats->nodeStats.m_last_recv); }
@@
-    QString timeOffset() const { return GUIUtil::formatTimeOffset(m_combinedStats->nodeStats.nTimeOffset); }
+    QString timeOffset() const { return GUIUtil::formatTimeOffset(m_combinedStats->nodeStateStats.time_offset.count()); }
```

## `2a11d121d5` - `Merge bitcoin-core/gui-qml#401: Introduce Wallet Select Dropdown`

Build status after fix: passed `bitcoin-qml` at first-parent position 214.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-214-2a11d121d5.patch
```

Failure found:

- `WalletListModel::listWalletDir()` iterated
  `m_node.walletLoader().listWalletDir()` as `std::string`.
- Current Core's wallet loader returns `(path, format)` pairs, so the build
  failed with invalid initialization of `const std::string&` from a pair.

Fix sources:

- Later branch state iterates `listWalletDir()` with structured bindings.
- At this earlier commit only the wallet name/path is displayed, so the format
  value is intentionally ignored until later wallet-list roles are added.

Patch hunk to amend into `2a11d121d5`:

```diff
diff --git a/src/qml/models/walletlistmodel.cpp b/src/qml/models/walletlistmodel.cpp
@@
-    for (const std::string &name : m_node.walletLoader().listWalletDir()) {
+    for (const auto& [name, format] : m_node.walletLoader().listWalletDir()) {
+        Q_UNUSED(format);
         QString qname = QString::fromStdString(name);
```

## `c01ca8682b` - `Merge bitcoin-core/gui-qml#403: Introduce Create Single-Sig wallet flow`

Build status after fix: passed `bitcoin-qml` at first-parent position 213.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-213-c01ca8682b.patch
```

Failure found:

- Link failed with duplicate QObject metaobject symbols for `WalletController`.
- This commit introduced `src/qml/walletcontroller.*` with class
  `WalletController`, which collides with the existing Qt Widgets
  `src/qt/walletcontroller.*` class when both libraries are linked into
  `bitcoin-qml`.

Fix sources:

- Later branch state uses `WalletQmlController` for the QML controller and
  keeps the QML context property named `walletController`.
- `4ddf0e9418` deletes `walletcontroller.*` and introduces
  `walletqmlcontroller.*`; the minimal fix for this earlier commit is to rename
  the class symbol immediately while leaving file paths unchanged until the
  later replacement commit.

Patch hunks to amend into `c01ca8682b`:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-    WalletController wallet_controller(*node);
+    WalletQmlController wallet_controller(*node);
diff --git a/src/qml/walletcontroller.h b/src/qml/walletcontroller.h
@@
-class WalletController : public QObject
+class WalletQmlController : public QObject
@@
-    explicit WalletController(interfaces::Node& node);
+    explicit WalletQmlController(interfaces::Node& node);
diff --git a/src/qml/walletcontroller.cpp b/src/qml/walletcontroller.cpp
@@
-WalletController::WalletController(interfaces::Node& node)
+WalletQmlController::WalletQmlController(interfaces::Node& node)
@@
-void WalletController::createSingleSigWallet(const QString& name, const QString& passphrase)
+void WalletQmlController::createSingleSigWallet(const QString& name, const QString& passphrase)
```

## `4ffe0929d7` - `Merge bitcoin-core/gui-qml#397: UI Only Custom Datadir Display`

Build status after fix: passed `bitcoin-qml` at first-parent position 212.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-212-4ffe0929d7.patch
```

Failure found:

- The previous accumulated patch conflicted in `OptionsQmlModel` where this
  commit added persistent `m_dataDir` state and changed custom datadir methods.

Fix sources:

- `4ffe0929d7` supplies `m_dataDir = getDefaultDataDirString()` and the datadir
  display state.
- The carried fix from `808ee11307` still replaces the removed
  `DEFAULT_UPNP` symbol with current Core's `DEFAULT_NATPMP`.

Patch hunk to amend into `4ffe0929d7`:

```diff
diff --git a/src/qml/models/options_model.cpp b/src/qml/models/options_model.cpp
@@
-    m_upnp = SettingToBool(m_node.getPersistentSetting("upnp"), DEFAULT_UPNP);
+    m_upnp = SettingToBool(m_node.getPersistentSetting("upnp"), DEFAULT_NATPMP);

     m_dataDir = getDefaultDataDirString();
```

## `808ee11307` - `Merge bitcoin-core/gui-qml#284: Only write options after onboarding`

Build status after fix: passed `bitcoin-qml` at first-parent position 210.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-210-808ee11307.patch
```

Failures found:

- The previous accumulated patch conflicted in `OptionsQmlModel` because this
  commit added the `m_onboarded` constructor parameter and only writes settings
  after onboarding.
- After resolving that conflict, the current Core build failed because
  `DEFAULT_UPNP` no longer exists.

Fix sources:

- `808ee11307` supplies the onboarding-aware settings writes.
- `fa5672dcaf` supplies the `SettingTo<int64_t>` conversion.
- `275945b23e` supplies `DEFAULT_DB_CACHE >> 20` and cache headers.
- Current `mapport.h` only exposes `DEFAULT_NATPMP`; there is no
  `DEFAULT_UPNP` symbol in the current Core base. The still-present QML `upnp`
  field was defaulted to `DEFAULT_NATPMP` here until later option-model changes
  remove or reshape this setting.

Patch hunks to amend into `808ee11307`:

```diff
diff --git a/src/qml/models/options_model.cpp b/src/qml/models/options_model.cpp
@@
 #include <interfaces/node.h>
 #include <mapport.h>
+#include <node/caches.h>
+#include <node/chainstatemanager_args.h>
@@
-    int64_t prune_value{SettingToInt(m_node.getPersistentSetting("prune"), 0)};
+    int64_t prune_value{SettingTo<int64_t>(m_node.getPersistentSetting("prune"), 0)};
@@
-    m_script_threads = SettingToInt(m_node.getPersistentSetting("par"), DEFAULT_SCRIPTCHECK_THREADS);
+    m_script_threads = SettingTo<int64_t>(m_node.getPersistentSetting("par"), DEFAULT_SCRIPTCHECK_THREADS);
@@
-    m_upnp = SettingToBool(m_node.getPersistentSetting("upnp"), DEFAULT_UPNP);
+    m_upnp = SettingToBool(m_node.getPersistentSetting("upnp"), DEFAULT_NATPMP);
@@
-    if (m_dbcache_size_mib != nDefaultDbCache) {
+    if (m_dbcache_size_mib != DEFAULT_DB_CACHE >> 20) {
         m_node.updateRwSetting("dbcache", m_dbcache_size_mib);
     }
```

## `ba6b08f0c7` - `Merge bitcoin-core/gui-qml#392: UI Only Custom Datadir`

Build status after fix: passed `bitcoin-qml` at first-parent position 207.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-207-ba6b08f0c7.patch
```

Failure found:

- The custom datadir helper added `QString::fromStdString(path.u8string())`.
- In the current C++20 build, `fs::path::u8string()` returns `std::u8string`,
  which cannot be passed to `QString::fromStdString(const std::string&)`.

Fix sources:

- Later branch head contains the same helper as
  `QString::fromStdString(path.utf8string())` in
  `src/qml/models/options_model.cpp`.
- The underlying filesystem compatibility helper is exposed by current
  `src/util/fs.h`.

Patch hunk to amend into `ba6b08f0c7`:

```diff
diff --git a/src/qml/models/options_model.cpp b/src/qml/models/options_model.cpp
@@
 QString PathToQString(const fs::path &path)
 {
-    return QString::fromStdString(path.u8string());
+    return QString::fromStdString(path.utf8string());
 }
```

## `01c0847b69` - `Merge bitcoin-core/gui-qml#360: Fix QSettings initialization failure on startup when parsing invalid arguments`

Build status after fix: passed `bitcoin-qml` at first-parent position 203.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-203-01c0847b69.patch
```

Failure found:

- The previous accumulated patch failed a normal context apply in
  `src/qml/bitcoin.cpp` because this commit moved
  `setOrganizationName`/`setOrganizationDomain`/`setApplicationName` before
  command-line parsing so invalid arguments can still show the QML error dialog.

Fix sources:

- `01c0847b69` supplies the QSettings startup-order fix.
- The carried API fixes are unchanged from `11f5ea3b37`; a three-way apply kept
  the startup-order change and the current-Core `InitError` wrappers.

Patch detail:

```text
git apply --3way /tmp/gui-qml-staging-buildwalk-logs/fix-through-186-11f5ea3b37.patch
```

## `11f5ea3b37` - `Merge bitcoin-core/gui-qml#359: Sync with the main repo`

Build status after fix: passed `bitcoin-qml` at first-parent position 186.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-186-11f5ea3b37.patch
```

Failure found:

- The previous accumulated patch overlapped with this sync in
  `src/qml/bitcoin.cpp`, `src/qml/models/options_model.cpp`, and
  `src/qml/models/options_model.h`.
- This commit already brought in `common/args.h`, `common/system.h`,
  `CheckDataDirOption(gArgs)`, `SelectParams(gArgs.GetChainType())`, and
  `ChainTypeToString(gArgs.GetChainType())` usage, but later branch fixes still
  use `gArgs.GetChainTypeString()`, current `InitError` wrapping, and the newer
  dbcache constants.

Fix sources:

- `11f5ea3b37` is the sync source for the common-header split and partial
  chain-type update.
- `fa5672dcaf` supplies `SettingTo<int64_t>`.
- `275945b23e` supplies the current dbcache headers and constants.
- Current `ArgsManager` provides `GetChainTypeString()`, which replaced the
  intermediate `ChainTypeToString(gArgs.GetChainType())` form.

Patch hunks resolved at this checkpoint:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-    chain_model.setCurrentNetworkName(QString::fromStdString(ChainTypeToString(gArgs.GetChainType())));
+    chain_model.setCurrentNetworkName(QString::fromStdString(gArgs.GetChainTypeString()));
     setupChainQSettings(&app, chain_model.currentNetworkName());
diff --git a/src/qml/models/options_model.h b/src/qml/models/options_model.h
@@
-#include <txdb.h>
 #include <common/settings.h>
 #include <common/system.h>
+#include <node/caches.h>
+#include <node/chainstatemanager_args.h>
 #include <validation.h>
```

## `ab562faad0` - `Merge bitcoin-core/gui-qml#331: Use node model state to update the android notification`

Build status after fix: passed `bitcoin-qml` at first-parent position 178.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-178-ab562faad0.patch
```

Failure found:

- The previous accumulated patch failed a normal context apply in
  `src/qml/bitcoin.cpp` after this commit added Android notifier setup beside
  `NetworkTrafficTower`.

Fix sources:

- `ab562faad0` supplies the `AndroidNotifier android_notifier{node_model}` setup.
- The carried fix remains the same Core-API adaptation from the prior
  checkpoints. A three-way apply preserved the Android notifier context without
  needing additional source changes.

Patch detail:

```text
git apply --3way /tmp/gui-qml-staging-buildwalk-logs/fix-through-173-893ee33d74.patch
```

## `893ee33d74` - `Merge bitcoin-core/gui-qml#335: Move backend models into models directory`

Build status after fix: passed `bitcoin-qml` at first-parent position 173.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-173-893ee33d74.patch
```

Failure found:

- The previous accumulated patch referenced model files at the old
  `src/qml/*.cpp` and `src/qml/*.h` paths.
- This commit moved backend model files under `src/qml/models/`, so Git could
  not apply the carried fixes to `chainmodel`, `networktraffictower`,
  `nodemodel`, and `options_model` without path adjustment.

Fix sources:

- `893ee33d74` is the structural source for the new model paths.
- The semantic fixes are unchanged from the earlier checkpoints:
  `8bfdea5801` for keeping Core headers out of `chainmodel.h`,
  `89d96d04ab`/`fa5672dcaf`/`275945b23e` for `OptionsQmlModel`,
  `f227be9f2c` for the peer-count callback, and `745936d16a`/`1f7fe67f13`
  for Qt 6 container-size casts.

Mechanical patch-path rewrite used before validating this checkpoint:

```sh
perl -pe 's#src/qml/chainmodel#src/qml/models/chainmodel#g; s#src/qml/networktraffictower#src/qml/models/networktraffictower#g; s#src/qml/nodemodel#src/qml/models/nodemodel#g; s#src/qml/options_model#src/qml/models/options_model#g; s#<qml/chainmodel\\.h>#<qml/models/chainmodel.h>#g; s#<qml/networktraffictower\\.h>#<qml/models/networktraffictower.h>#g; s#<qml/nodemodel\\.h>#<qml/models/nodemodel.h>#g; s#<qml/options_model\\.h>#<qml/models/options_model.h>#g' \
  /tmp/gui-qml-staging-buildwalk-logs/fix-through-169-5ad6a347af.patch \
  > /tmp/gui-qml-staging-buildwalk-logs/fix-through-169-5ad6a347af-modelpaths.patch
```

## `5ad6a347af` - `Merge bitcoin-core/gui-qml#332: Sync with the main repo`

Build status after fix: passed `bitcoin-qml` at first-parent position 169.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-169-5ad6a347af.patch
```

Failure found:

- The previous accumulated patch did not apply to `src/qml/bitcoin.cpp`.
- This sync commit already included some of the earlier initialization API
  changes, including `CheckDataDirOption(gArgs)`, so the patch overlapped on
  the surrounding `InitError` call.

Fix sources:

- `5ad6a347af` itself provides part of the sync, including the updated
  `CheckDataDirOption(gArgs)` call.
- `25a52764ca qml: adapt UI callbacks to Core v31` and later branch syncs
  provide the no-caption UI callback and `Untranslated(strprintf(...))` error
  construction style used by current Core.

Patch hunk to amend into `5ad6a347af` after applying the previous accumulated
fixes:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
     /// Determine availability of data directory.
     if (!CheckDataDirOption(gArgs)) {
-        InitError(strprintf(Untranslated("Specified data directory \"%s\" does not exist.\n"), gArgs.GetArg("-datadir", "")));
+        InitError(Untranslated(strprintf("Specified data directory \"%s\" does not exist.\n", gArgs.GetArg("-datadir", ""))));
         return EXIT_FAILURE;
     }
```

## `81a37b5412` - `qml: setup QSettings registration`

Build status after fix: passed `bitcoin-qml` at first-parent position 163.

Validated accumulated patch:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-163-81a37b5412.patch
```

Failure found:

- The previous accumulated compatibility patch no longer applied cleanly to
  `src/qml/bitcoin.cpp` after this commit added the chain-specific QSettings
  setup call beside the network-name initialization.

Fix sources:

- `8bfdea5801` and earlier compatibility fix checkpoints for the carried
  Core-API adaptations.
- This commit's own `setupChainQSettings(&app, chain_model.currentNetworkName())`
  call must be preserved.
- The branch-later Core API fix changes the network-name source from
  `gArgs.GetChainName()` to `gArgs.GetChainTypeString()`.

Patch hunk to amend into `81a37b5412` after applying the previous accumulated
fixes:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
     NetworkTrafficTower network_traffic_tower{node_model};

     ChainModel chain_model{*chain};
-    chain_model.setCurrentNetworkName(QString::fromStdString(gArgs.GetChainName()));
+    chain_model.setCurrentNetworkName(QString::fromStdString(gArgs.GetChainTypeString()));
     setupChainQSettings(&app, chain_model.currentNetworkName());

     QObject::connect(&node_model, &NodeModel::setTimeRatioList, &chain_model, &ChainModel::setTimeRatioList);
```

The walk starts at `12b5c02698 cmake: Incorporate `qml` subdirectory`.
`1668daab16 cmake: Add `bitcoin-qml` executable` creates
`src/qml/CMakeLists.txt`, but the top-level build cannot see the
`bitcoin-qml` target until `12b5c02698`.

## `642d4de621` `qml: Add bitcoin module`

Status: validated.

Validation log:

```text
/tmp/gui-qml-staging-buildwalk-logs/002-642d4de621-bootstrap2-build.log
```

Failures found:

- `node/ui_interface.h` no longer exists in the current Core tree.
- `util/system.h` no longer provides the argument APIs used here.
- `NodeContext` now lives in namespace `node`.
- `interfaces::MakeNode` now takes `node::NodeContext&`, not a pointer.
- `CClientUIInterface::*_connect` now returns `btcsignals::connection`,
  making the old `boost::signals2::scoped_connection` declarations invalid.
- `strprintf(Untranslated(...), ...)` no longer matches the current
  translation formatting API.

Fix sources:

- `fe004357e1 Merge bitcoin-core/gui-qml#137: Sync with the main repo`
  changes `node/ui_interface.h` to `node/interface_ui.h`.
- `11f5ea3b37 Merge bitcoin-core/gui-qml#359: Sync with the main repo`
  shows the `util/system.h` split toward `common/args.h`/`common/system.h`.
- Current `src/interfaces/node.h` declares
  `std::unique_ptr<Node> MakeNode(node::NodeContext& context)`.
- Current `src/node/interface_ui.h` declares the UI connection wrappers as
  `btcsignals::connection`.

Patch to amend into `642d4de621`:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
index a815ad155a..561f33e789 100644
--- a/src/qml/bitcoin.cpp
+++ b/src/qml/bitcoin.cpp
@@ -7,13 +7,13 @@
 #include <init.h>
 #include <interfaces/node.h>
 #include <node/context.h>
-#include <node/ui_interface.h>
+#include <node/interface_ui.h>
 #include <noui.h>
 #include <qt/guiconstants.h>
-#include <util/system.h>
+#include <common/args.h>
 #include <util/translation.h>

-#include <boost/signals2/connection.hpp>
+#include <btcsignals.h>
 #include <memory>
@@ -32,13 +32,13 @@ void SetupUIArgs(ArgsManager& argsman)
 int QmlGuiMain(int argc, char* argv[])
 {
-    NodeContext node_context;
-    std::unique_ptr<interfaces::Node> node = interfaces::MakeNode(&node_context);
+    node::NodeContext node_context;
+    std::unique_ptr<interfaces::Node> node = interfaces::MakeNode(node_context);

     // Subscribe to global signals from core
-    boost::signals2::scoped_connection handler_message_box = ::uiInterface.ThreadSafeMessageBox_connect(noui_ThreadSafeMessageBox);
-    boost::signals2::scoped_connection handler_question = ::uiInterface.ThreadSafeQuestion_connect(noui_ThreadSafeQuestion);
-    boost::signals2::scoped_connection handler_init_message = ::uiInterface.InitMessage_connect(noui_InitMessage);
+    auto handler_message_box = ::uiInterface.ThreadSafeMessageBox_connect(noui_ThreadSafeMessageBox);
+    auto handler_question = ::uiInterface.ThreadSafeQuestion_connect(noui_ThreadSafeQuestion);
+    auto handler_init_message = ::uiInterface.InitMessage_connect(noui_InitMessage);
@@ -49,7 +49,7 @@ int QmlGuiMain(int argc, char* argv[])
     SetupUIArgs(gArgs);
     std::string error;
     if (!gArgs.ParseParameters(argc, argv, error)) {
-        InitError(strprintf(Untranslated("Error parsing command line arguments: %s\n"), error));
+        InitError(Untranslated(strprintf("Error parsing command line arguments: %s\n", error)));
         return EXIT_FAILURE;
    }
```

## `42e0c4fdcb` - `Merge bitcoin-core/gui-qml#224: Initial support and wiring for developer settings`

Validation:

- Broken hash: `42e0c4fdcb`.
- Baseline failure: the accumulated patch through `2c2de256c8` no longer applied because this merge expands `OptionsQmlModel` with developer settings (`dbcache`, `par`) and changes the include/default-value context in `src/qml/options_model.cpp`.
- Additional compile failures after context rebasing:
  - `nDefaultDbCache` was not declared.
  - `DEFAULT_SCRIPTCHECK_THREADS` was not visible from the previous include set.
- Source fix:
  - `275945b23e` (`qml: adapt options model to Core v31 APIs`) converts QML option model calls from `SettingToInt(...)` to `SettingTo<int64_t>(...)`.
  - Current-base constants come from `node/caches.h` (`DEFAULT_DB_CACHE`) and `node/chainstatemanager_args.h` (`DEFAULT_SCRIPTCHECK_THREADS`).
  - Earlier `89d96d04ab` still provides the `common/settings.h` and `common/system.h` migration.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/121-42e0c4fdcb-manual2-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-121-42e0c4fdcb.patch`.

Minimal patch:

```diff
diff --git a/src/qml/options_model.cpp b/src/qml/options_model.cpp
@@
+#include <common/args.h>
+#include <common/settings.h>
+#include <common/system.h>
 #include <interfaces/node.h>
+#include <node/caches.h>
+#include <node/chainstatemanager_args.h>
@@
-#include <util/settings.h>
-#include <util/system.h>
@@
-    m_dbcache_size_mib = SettingToInt(m_node.getPersistentSetting("dbcache"), nDefaultDbCache);
+    m_dbcache_size_mib = SettingTo<int64_t>(m_node.getPersistentSetting("dbcache"), DEFAULT_DB_CACHE >> 20);
@@
-    int64_t prune_value{SettingToInt(m_node.getPersistentSetting("prune"), 0)};
+    int64_t prune_value{SettingTo<int64_t>(m_node.getPersistentSetting("prune"), 0)};
@@
-    m_script_threads = SettingToInt(m_node.getPersistentSetting("par"), DEFAULT_SCRIPTCHECK_THREADS);
+    m_script_threads = SettingTo<int64_t>(m_node.getPersistentSetting("par"), DEFAULT_SCRIPTCHECK_THREADS);
@@
-util::SettingsValue OptionsQmlModel::pruneSetting() const
+common::SettingsValue OptionsQmlModel::pruneSetting() const
```

## `d0167a5b81` - `Merge bitcoin-core/gui-qml#236: Introduce PeersIndicator component, Add to BlockClock`

Validation:

- Broken hash: `d0167a5b81`.
- Baseline failure:
  - `src/qml/nodemodel.cpp:149:16: error: 'PeersNumByType' has not been declared`.
  - The current `interfaces::Node::NotifyNumConnectionsChangedFn` is `std::function<void(int new_num_connections)>`.
- Source fix:
  - `f227be9f2c` / `c6d5db136a` (`temporarily revert PeersNumByType (needs follow-up)`) from `bitcoin-core/gui-qml#475`.
  - These commits explicitly revert the branch-only `PeersNumByType` notification because upstream Bitcoin Core only provides an integer total connection count.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/122-d0167a5b81-manual-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-122-d0167a5b81.patch`.

Minimal patch:

```diff
diff --git a/src/qml/nodemodel.cpp b/src/qml/nodemodel.cpp
@@
    m_handler_notify_num_peers_changed = m_node.handleNotifyNumConnectionsChanged(
-        [this](PeersNumByType new_num_peers) {
-            setNumOutboundPeers(new_num_peers.outbound_full_relay + new_num_peers.block_relay);
+        [this](int new_num_connections) {
+            setNumOutboundPeers(new_num_connections);
         });
```

## `9924c0c44b` - `Merge bitcoin-core/gui-qml#251: Introduce and Use NetworkIndicator component`

Validation:

- Broken hash: `9924c0c44b`.
- Baseline failure:
  - `src/qml/bitcoin.cpp:179:68: error: 'class ArgsManager' has no member named 'GetChainName'; did you mean 'GetChainType'?`
- Source fix:
  - Final staging uses `gArgs.GetChainTypeString()` at `src/qml/bitcoin.cpp`.
  - The source migration is the chain-type refactor already represented by `89d96d04ab` (`Adjust code according to changes in the main repository`) and `ba8fc7d788` (`refactor: Replace string chain name constants with ChainTypes`).
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/125-9924c0c44b-manual-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-125-9924c0c44b.patch`.

Minimal patch:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-    chain_model.setCurrentNetworkName(QString::fromStdString(gArgs.GetChainName()));
+    chain_model.setCurrentNetworkName(QString::fromStdString(gArgs.GetChainTypeString()));
```

## `1d6c2d4de0` - `Merge bitcoin-core/gui-qml#259: Introduce the Peers page`

Validation:

- Broken hash: `1d6c2d4de0`.
- Baseline failure: the accumulated patch through `9924c0c44b` no longer applied because this merge adds Peers page wiring to `src/qml/bitcoin.cpp`, including `interfaces::Chain`, `PeerTableModel`, `PeerListSortProxy`, and extra QML context properties near the same include and setup blocks.
- Source fix: no new semantic source fix was required at this hash; replay the accumulated fixes from prior sections while preserving the peer-model wiring introduced here.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/136-1d6c2d4de0-manual-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-136-1d6c2d4de0.patch`.

Context note:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
 #include <qt/networkstyle.h>
 #include <qt/peertablemodel.h>
-#include <util/system.h>
+#include <common/args.h>
+#include <common/system.h>
@@
     PeerTableModel peer_model{*node, nullptr};
     PeerListSortProxy peer_model_sort_proxy{nullptr};
     peer_model_sort_proxy.setSourceModel(&peer_model);
```

## `96834722fb` - `Merge bitcoin-core/gui-qml#247: Only show Onboarding if settings file is missing`

Validation:

- Broken hash: `96834722fb`.
- Baseline failure: the accumulated patch through `1d6c2d4de0` no longer applied because this merge adds `ConfigurationFileExists(...)` and `needOnboarding` logic to `src/qml/bitcoin.cpp` near the same startup/settings blocks.
- Additional compile failure after rebasing:
  - `AbsPathForConfigVal(rel_config_path, true)` no longer matches the current signature.
- Source fix:
  - Preserve the onboarding logic from `96834722fb`.
  - Apply the current `AbsPathForConfigVal(const ArgsManager&, const fs::path&, bool)` signature from `common/args.h`.
  - Keep the accumulated common args/settings, chain-type, network-style, options-model, block-clock, and peer-count fixes from prior sections.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/145-96834722fb-manual2-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-145-96834722fb.patch`.

Minimal additional patch:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-    const fs::path abs_config_path = AbsPathForConfigVal(rel_config_path, true);
+    const fs::path abs_config_path = AbsPathForConfigVal(argsman, rel_config_path, true);
```

## `260482baf2` - `Merge bitcoin-core/gui-qml#245: Custom Prune OptionButton`

Validation:

- Broken hash: `260482baf2`.
- Baseline failure: the accumulated patch through `96834722fb` no longer applied because this merge changes `OptionsQmlModel`'s header layout, adding dbcache/script-thread min/max properties around the same `util/settings.h`, `util/system.h`, and `util::SettingsValue` context.
- Source fix:
  - Same options model API sources as earlier: `89d96d04ab` for `common/settings.h` and `common/system.h`, `275945b23e` for `SettingTo<int64_t>(...)`, and the current `node/caches.h` / `node/chainstatemanager_args.h` constants.
  - Additional constants at this shape:
    - `nMinDbCache` -> `MIN_DB_CACHE >> 20`.
    - `nMaxDbCache` -> `MAX_COINS_DB_CACHE >> 20`.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/147-260482baf2-manual-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-147-260482baf2.patch`.

Minimal patch:

```diff
diff --git a/src/qml/options_model.h b/src/qml/options_model.h
@@
-#include <txdb.h>
-#include <util/settings.h>
-#include <util/system.h>
+#include <common/settings.h>
+#include <common/system.h>
+#include <node/caches.h>
+#include <node/chainstatemanager_args.h>
@@
-    const int m_min_dbcache_size_mib{nMinDbCache};
-    const int m_max_dbcache_size_mib{nMaxDbCache};
+    const int m_min_dbcache_size_mib{MIN_DB_CACHE >> 20};
+    const int m_max_dbcache_size_mib{MAX_COINS_DB_CACHE >> 20};
@@
-    util::SettingsValue pruneSetting() const;
+    common::SettingsValue pruneSetting() const;
```

## `7b5e5f5a62` - `Merge bitcoin-core/gui-qml#286: Introduce Network Traffic node page`

Validation:

- Broken hash: `7b5e5f5a62`.
- Baseline failure: the accumulated patch through `260482baf2` no longer applied because this merge adds Network Traffic wiring to `src/qml/bitcoin.cpp`, including `NetworkTrafficTower`, `LineGraph`, and new QML context/type registrations.
- Additional compile failures after context rebasing:
  - `std::min(m_max_samples, m_value_list.size())` failed because Qt 6 `QQueue/QList::size()` returns `qsizetype`.
  - The same `std::min(...)` type mismatch appeared in `NetworkTrafficTower`.
- Source fix:
  - Context-only rebase for the new network-traffic wiring.
  - `745936d16a` / `1f7fe67f13` (`QQueue requires cast qtsizetype to int`) from `bitcoin-core/gui-qml#475`.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/154-7b5e5f5a62-manual2-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-154-7b5e5f5a62.patch`.

Minimal Qt 6 patch:

```diff
diff --git a/src/qml/controls/linegraph.cpp b/src/qml/controls/linegraph.cpp
@@
-    int item_count = std::min(m_max_samples, m_value_list.size());
+    int item_count = std::min(m_max_samples, static_cast<int>(m_value_list.size()));
diff --git a/src/qml/networktraffictower.cpp b/src/qml/networktraffictower.cpp
@@
-    int filter_window_size = std::min(rate_list->size(), m_filter_window_size);
+    int filter_window_size = std::min(static_cast<int>(rate_list->size()), m_filter_window_size);
@@
-    int lookback = std::min(smoothed_rate_list->size() - 1, m_filter_window_size * 10);
+    int lookback = std::min(static_cast<int>(smoothed_rate_list->size()) - 1, m_filter_window_size * 10);
```

## `3964ccebf0` - `Merge bitcoin-core/gui-qml#278: Smart storage values based on assumed chain and chainstate values`

Validation:

- Broken hash: `3964ccebf0`.
- Baseline failure:
  - Qt moc failed on `src/qml/chainmodel.h` with `Parse error at "std"`.
  - The immediate cause is that `chainmodel.h` includes Core headers (`chainparams.h`, via transitive C++20 library headers) inside a QObject header processed by moc.
- Source fix:
  - `8bfdea5801` (`qml: keep Core headers out of chain model moc`) moves Core headers from `chainmodel.h` into `chainmodel.cpp` and initializes the assumed chain sizes in the constructor initializer list.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/155-3964ccebf0-manual-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-155-3964ccebf0.patch`.

Minimal patch:

```diff
diff --git a/src/qml/chainmodel.h b/src/qml/chainmodel.h
@@
-#include <chainparams.h>
-#include <interfaces/chain.h>
@@
-    quint64 m_assumed_blockchain_size{ Params().AssumedBlockchainSize() };
-    quint64 m_assumed_chainstate_size{ Params().AssumedChainStateSize() };
+    quint64 m_assumed_blockchain_size;
+    quint64 m_assumed_chainstate_size;
diff --git a/src/qml/chainmodel.cpp b/src/qml/chainmodel.cpp
@@
+#include <chainparams.h>
+#include <interfaces/chain.h>
@@
-    : m_chain{chain}
+    : m_assumed_blockchain_size{Params().AssumedBlockchainSize()}
+    , m_assumed_chainstate_size{Params().AssumedChainStateSize()}
+    , m_chain{chain}
```

## `9351b62d4f` `qml: Add stub window`

Status: validated.

Validation log:

```text
/tmp/gui-qml-staging-buildwalk-logs/003-9351b62d4f-resource-build.log
```

Failures found:

- Same bootstrap API failures as `642d4de621`, with slightly different
  `bitcoin.cpp` context after the stub window load code is added.
- Link failure: `undefined reference to qInitResources_bitcoin_qml()` because
  `Q_INIT_RESOURCE(bitcoin_qml)` is added before the later CMake resource
  embedding commit.

Fix sources:

- Same API fix sources listed for `642d4de621`.
- `3c14dd1356 cmake: Embed QML resources` adds the required
  `qt6_add_resources()` wiring for `src/qml/bitcoin_qml.qrc`.

Patch shape to amend into `9351b62d4f`:

```diff
diff --git a/src/qml/CMakeLists.txt b/src/qml/CMakeLists.txt
@@
 add_library(bitcoinqml STATIC
   bitcoin.cpp
 )

+set(QML_QRC "${CMAKE_CURRENT_SOURCE_DIR}/bitcoin_qml.qrc")
+qt6_add_resources(QML_QRC_CPP ${QML_QRC})
+target_sources(bitcoinqml
+  PRIVATE
+    ${QML_QRC_CPP}
+)
+
 target_compile_definitions(bitcoinqml
   PUBLIC
     QT_NO_KEYWORDS
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-#include <node/ui_interface.h>
+#include <node/interface_ui.h>
@@
-#include <util/system.h>
+#include <common/args.h>
@@
-#include <boost/signals2/connection.hpp>
+#include <btcsignals.h>
@@
-    NodeContext node_context;
-    std::unique_ptr<interfaces::Node> node = interfaces::MakeNode(&node_context);
+    node::NodeContext node_context;
+    std::unique_ptr<interfaces::Node> node = interfaces::MakeNode(node_context);
@@
-    boost::signals2::scoped_connection handler_message_box = ::uiInterface.ThreadSafeMessageBox_connect(noui_ThreadSafeMessageBox);
-    boost::signals2::scoped_connection handler_question = ::uiInterface.ThreadSafeQuestion_connect(noui_ThreadSafeQuestion);
-    boost::signals2::scoped_connection handler_init_message = ::uiInterface.InitMessage_connect(noui_InitMessage);
+    auto handler_message_box = ::uiInterface.ThreadSafeMessageBox_connect(noui_ThreadSafeMessageBox);
+    auto handler_question = ::uiInterface.ThreadSafeQuestion_connect(noui_ThreadSafeQuestion);
+    auto handler_init_message = ::uiInterface.InitMessage_connect(noui_InitMessage);
@@
-        InitError(strprintf(Untranslated("Error parsing command line arguments: %s\n"), error));
+        InitError(Untranslated(strprintf("Error parsing command line arguments: %s\n", error)));
```

## `238b13c76c` `Merge bitcoin-core/gui-qml#11: Add basic start/shutdown functionality`

Status: validated.

Validation log:

```text
/tmp/gui-qml-staging-buildwalk-logs/005-238b13c76c-cmake-sources-build.log
```

Failures found:

- Same current-Core bootstrap API failures in the rewritten `bitcoin.cpp`.
- Link failure for `NodeModel` vtable/signals because the QML library still
  only compiled `bitcoin.cpp`.

Fix sources:

- Same API fix sources listed for `642d4de621`.
- `3c14dd1356 cmake: Embed QML resources`.
- `a64844ecc7 cmake: Build QML sources from src/qml` adds the recursive source
  list and supporting link dependencies needed as soon as `NodeModel` and
  `InitExecutor` are used.

Patch shape to amend into `238b13c76c`:

```diff
diff --git a/src/qml/CMakeLists.txt b/src/qml/CMakeLists.txt
@@
-set(CMAKE_AUTOMOC ON)
-
-add_library(bitcoinqml STATIC
-  bitcoin.cpp
-)
+set(CMAKE_AUTOMOC ON)
+
+option(ENABLE_TEST_AUTOMATION "Enable test automation bridge for QML UI testing" OFF)
+
+set(QML_QRC "${CMAKE_CURRENT_SOURCE_DIR}/bitcoin_qml.qrc")
+qt6_add_resources(QML_QRC_CPP ${QML_QRC})
+
+file(GLOB_RECURSE QML_SOURCES
+  "${CMAKE_CURRENT_SOURCE_DIR}/*.cpp"
+  "${CMAKE_CURRENT_SOURCE_DIR}/*.h"
+)
+list(FILTER QML_SOURCES EXCLUDE REGEX "/main\\.cpp$")
+list(FILTER QML_SOURCES EXCLUDE REGEX "/androidnotifier\\.(cpp|h)$")
+if(NOT ENABLE_TEST_AUTOMATION)
+  list(FILTER QML_SOURCES EXCLUDE REGEX "/test/")
+endif()
+list(APPEND QML_SOURCES ${QML_QRC_CPP})
+
+add_library(bitcoinqml STATIC ${QML_SOURCES})
@@
 target_compile_definitions(bitcoinqml
   PUBLIC
     QT_NO_KEYWORDS
     QT_USE_QSTRINGBUILDER
 )
+if(ENABLE_TEST_AUTOMATION)
+  target_compile_definitions(bitcoinqml PUBLIC ENABLE_TEST_AUTOMATION)
+endif()
@@
 target_link_libraries(bitcoinqml
   PUBLIC
     core_interface
     bitcoin_node
+    univalue
+    Boost::headers
+    $<TARGET_NAME_IF_EXISTS:QRencode::QRencode>
     Qt6::Qml
-    Qt6::Widgets
     Qt6::Quick
+    Qt6::QuickControls2
+    Qt6::Network
+    Qt6::Widgets
 )
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-#include <node/ui_interface.h>
+#include <node/interface_ui.h>
@@
-#include <util/system.h>
+#include <common/args.h>
@@
-        InitError(strprintf(Untranslated("Error parsing command line arguments: %s\n"), error));
+        InitError(Untranslated(strprintf("Error parsing command line arguments: %s\n", error)));
@@
-    CheckDataDirOption();
+    CheckDataDirOption(gArgs);
@@
-    SelectParams(gArgs.GetChainName());
+    SelectParams(gArgs.GetChainType());
@@
-    NodeContext node_context;
+    node::NodeContext node_context;
@@
-    std::unique_ptr<interfaces::Node> node = interfaces::MakeNode(&node_context);
+    std::unique_ptr<interfaces::Node> node = interfaces::MakeNode(node_context);
```

## `4def82824b` - `Merge bitcoin-core/gui-qml#42: Introduce ImageProvider class`

Validation:

- Broken hash: `4def82824b`.
- Baseline failure: the accumulated patch through `128838c6ba` no longer applied because this merge added `src/qml/imageprovider.h`, `src/qml/util.h`, `qt/guiutil.h`, `qt/networkstyle.h`, and other nearby includes to `src/qml/bitcoin.cpp`.
- After adapting the context, the build exposed a real current-base failure:
  - `CChainParams` has no `NetworkIDString()`.
  - `NetworkStyle::instantiate(...)` in current Qt code expects `ChainType`.
- Source fix:
  - Context-only adaptation comes from the local shape introduced by `4def82824b`.
  - Network-style API fix comes from later upstream/core refactor `ba8fc7d788` (`refactor: Replace string chain name constants with ChainTypes`) and the final staging call site at `fork/qml-staging:src/qml/bitcoin.cpp`.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/020-4def82824b-manual2-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-020-4def82824b.patch`.

Minimal additional patch over the previous accumulated fix:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-    QScopedPointer<const NetworkStyle> network_style{NetworkStyle::instantiate(Params().NetworkIDString())};
+    QScopedPointer<const NetworkStyle> network_style{NetworkStyle::instantiate(Params().GetChainType())};
```

## `4116120c39` - `Merge bitcoin-core/gui-qml#57: Include missed <cassert> headers`

Validation:

- Broken hash: `4116120c39`.
- Baseline failure: the accumulated patch through `4def82824b` did not apply cleanly to `src/qml/bitcoin.cpp` because this merge added `<cassert>` next to the same include block.
- Source fix: no new semantic fix was required at this hash; preserve the `<cassert>` addition from `4116120c39` while replaying the accumulated compatibility changes from earlier entries.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/022-4116120c39-manual-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-022-4116120c39.patch`.

Context-only patch detail:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-#include <boost/signals2/connection.hpp>
+#include <btcsignals.h>
 #include <cassert>
 #include <memory>
 #include <tuple>
```

## `a4e3568657` - `Merge bitcoin-core/gui-qml#72: Sync with the main repo`

Validation:

- Broken hash: `a4e3568657`.
- Baseline failure: the accumulated patch through `4116120c39` no longer applied because this sync commit already includes part of the earlier startup rebase:
  - `interfaces::MakeGuiInit(argc, argv)` replaces `MakeNodeInit(...)`.
  - The local `NodeContext` setup is removed.
- Source fix:
  - Startup rebase source is `a4e3568657` itself, from the sync with the main repo.
  - Remaining compatibility changes still come from the earlier sources recorded above: `fe004357e1`, `11f5ea3b37`, `25a52764ca`, `0ac8e6f137`, `ba8fc7d788`, `3c14dd1356`, and `a64844ecc7`.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/024-a4e3568657-manual-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-024-a4e3568657.patch`.

Patch note:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-    std::unique_ptr<interfaces::Init> init = interfaces::MakeNodeInit(node_context, argc, argv, unused_exit_status);
+    std::unique_ptr<interfaces::Init> init = interfaces::MakeGuiInit(argc, argv);
```

Do not replay the `MakeGuiInit(...)` hunk again when starting at this hash; it is already present in the commit.

## `fe004357e1` - `Merge bitcoin-core/gui-qml#137: Sync with the main repo`

Validation:

- Broken hash: `fe004357e1`.
- Baseline failure: the accumulated patch through `a4e3568657` no longer applied because this sync commit already includes the `node/ui_interface.h` to `node/interface_ui.h` rename.
- Source fix:
  - The UI interface include/API source is `fe004357e1` itself.
  - The remaining still-needed compatibility pieces continue to come from later branch/source commits recorded above.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/059-fe004357e1-manual-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-059-fe004357e1.patch`.

Patch note:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-#include <node/ui_interface.h>
+#include <node/interface_ui.h>
```

Do not replay this hunk at or after `fe004357e1`; it is already present in the branch.

## `9b7465f678` - `Merge bitcoin-core/gui-qml#207: Introduce OptionsModel backend, Wire up Storage Amount settings to backend`

Validation:

- Broken hash: `9b7465f678`.
- Baseline failure:
  - `src/qml/options_model.h:8:10: fatal error: util/settings.h: No such file or directory`.
  - After switching settings headers, `src/qml/options_model.cpp` also failed on `util/system.h`.
  - After switching system headers, `SettingToInt(...)` was no longer available in the current base.
- Source fix:
  - `89d96d04ab` (`Adjust code according to changes in the main repository`) migrates QML options model includes from `util/settings.h` and `util/system.h` to `common/settings.h` and `common/system.h`, and changes `util::SettingsValue` to `common::SettingsValue`.
  - `fa5672dcaf` (`refactor: [gui] Use SettingTo<int64_t> over deprecated SettingToInt`) removes the deprecated `SettingToInt(...)` helper and uses `SettingTo<int64_t>(...)`.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/109-9b7465f678-manual4-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-109-9b7465f678.patch`.

Minimal patch:

```diff
diff --git a/src/qml/options_model.cpp b/src/qml/options_model.cpp
@@
+#include <common/args.h>
+#include <common/settings.h>
+#include <common/system.h>
 #include <interfaces/node.h>
@@
-#include <util/settings.h>
-#include <util/system.h>
@@
-    int64_t prune_value{SettingToInt(m_node.getPersistentSetting("prune"), 0)};
+    int64_t prune_value{SettingTo<int64_t>(m_node.getPersistentSetting("prune"), 0)};
@@
-util::SettingsValue OptionsQmlModel::pruneSetting() const
+common::SettingsValue OptionsQmlModel::pruneSetting() const
diff --git a/src/qml/options_model.h b/src/qml/options_model.h
@@
-#include <util/settings.h>
+#include <common/settings.h>
@@
-    util::SettingsValue pruneSetting() const;
+    common::SettingsValue pruneSetting() const;
```

## `2c2de256c8` - `Merge bitcoin-core/gui-qml#220: The Block Clock`

Validation:

- Broken hash: `2c2de256c8`.
- Baseline failure:
  - `src/qml/chainmodel.cpp:68:52: error: 'class interfaces::Chain' has no member named 'getBlockTime'; did you mean 'getBlockHash'?`
- Source fix:
  - `ccb7df8882` / `f2f96f6dad` (`use FoundBlock() interface instead of removed getBlockTime()`) from `bitcoin-core/gui-qml#475`.
  - These commits cite original `Rebased-From: 114053743b2ee49ff202d15ab8e429a3fa380b76`.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/112-2c2de256c8-manual-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-112-2c2de256c8.patch`.

Minimal patch:

```diff
diff --git a/src/qml/chainmodel.cpp b/src/qml/chainmodel.cpp
@@
 #include <QTime>
 #include <interfaces/chain.h>

+using interfaces::FoundBlock;
+
@@
     for (int height = first_block_height; height < active_chain_height + 1; height++) {
-        m_time_ratio_list.push_back(double(m_chain.getBlockTime(height) - time_at_meridian) / SECS_IN_12_HOURS);
+        uint256 block_hash{m_chain.getBlockHash(height)};
+        int64_t block_time;
+        m_chain.findBlock(block_hash, FoundBlock().time(block_time));
+        m_time_ratio_list.push_back(double(block_time - time_at_meridian) / SECS_IN_12_HOURS);
     }
```

## `7829a473bf` - `Merge bitcoin-core/gui-qml#222: Initial support and wiring for currently implemented connection settings`

Validation:

- Broken hash: `7829a473bf`.
- Baseline failure: the accumulated patch through `9b7465f678` no longer applied because this merge expands `OptionsQmlModel` with `listen`, `natpmp`, `server`, and `upnp` settings, shifting the same `pruneSetting()` declaration and implementation context.
- Source fix:
  - Same semantic fix as `9b7465f678`: `89d96d04ab` for the `common/settings.h` and `common/system.h` migration, and `fa5672dcaf` for `SettingTo<int64_t>(...)`.
  - This hash only needs a context rebase of that fix onto the larger options model.
- Validation log: `/tmp/gui-qml-staging-buildwalk-logs/111-7829a473bf-manual-build.log`.
- Reproduction patch: `/tmp/gui-qml-staging-buildwalk-logs/fix-through-111-7829a473bf.patch`.

Patch detail:

```diff
diff --git a/src/qml/options_model.cpp b/src/qml/options_model.cpp
@@
+#include <common/args.h>
+#include <common/settings.h>
+#include <common/system.h>
 #include <interfaces/node.h>
@@
-#include <util/settings.h>
-#include <util/system.h>
@@
-    int64_t prune_value{SettingToInt(m_node.getPersistentSetting("prune"), 0)};
+    int64_t prune_value{SettingTo<int64_t>(m_node.getPersistentSetting("prune"), 0)};
@@
-util::SettingsValue OptionsQmlModel::pruneSetting() const
+common::SettingsValue OptionsQmlModel::pruneSetting() const
diff --git a/src/qml/options_model.h b/src/qml/options_model.h
@@
-#include <util/settings.h>
+#include <common/settings.h>
@@
-    util::SettingsValue pruneSetting() const;
+    common::SettingsValue pruneSetting() const;
```

## `5071083ab5` `qml: Add message box for InitError calls`

Status: validated.

Validation log:

```text
/tmp/gui-qml-staging-buildwalk-logs/007-5071083ab5-compat-build.log
```

Failures found:

- Same API/CMake failures as `238b13c76c`.
- The new `InitErrorMessageBox` callback still used the old Core UI callback
  signature with a `caption` argument.

Fix sources:

- Same API/CMake fix sources listed for `238b13c76c`.
- `25a52764ca qml: adapt UI callbacks to Core v31`
  (`Rebased-From: 36c63267051f96cc7511e0d9488593824b3390ac`) removes the
  stale `caption` argument from `InitErrorMessageBox`.

Additional patch shape for this checkpoint:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
 bool InitErrorMessageBox(
     const bilingual_str& message,
-    [[maybe_unused]] const std::string& caption,
     [[maybe_unused]] unsigned int style)
```

## `c25b9968b3` `qml: Handle initialization errors`

Status: validated.

Validation log:

```text
/tmp/gui-qml-staging-buildwalk-logs/008-c25b9968b3-compat2-build.log
```

## `758cc610d3` `Merge bitcoin-core/gui-qml#24: Add GUIUtil::LogQtInfo() call`

Status: validated.

Validation log:

```text
/tmp/gui-qml-staging-buildwalk-logs/012-758cc610d3-compat-build.log
```

Intermediate checkpoints that built with the same accumulated patch before this
hash:

```text
ef8fe4f083 Merge bitcoin-core/gui-qml#19: build: Add required packages for static builds
cd2e2ee3ea Merge bitcoin-core/gui-qml#22: Check whether initerrormessage.qml is loaded correctly
37d2bc3215 Merge bitcoin-core/gui-qml#21: doc: Document runtime dependencies
```

Failures found:

- The accumulated patch could not apply because PR #24 adds
  `#include <qt/guiutil.h>` and `GUIUtil::LogQtInfo()` around the edited
  include/initialization region.
- Once adapted to the new context, the required fixes were the same recurring
  family as `c25b9968b3`: current Core include names, no-caption UI callback,
  `node::NodeContext`, `MakeNode(node_context)`, current argument/settings
  APIs, and CMake resource/source wiring.

Fix sources:

- Same fix sources listed for `c25b9968b3`.

Patch shape:

Use the `c25b9968b3` patch family above, preserving the newly added
`#include <qt/guiutil.h>` and `GUIUtil::LogQtInfo()` lines from PR #24. The
validated diff for this checkpoint was saved during the walk as:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-012-758cc610d3.patch
```

## `0b49e9d7e0` `Merge bitcoin-core/gui-qml#32: Log graphics API that is in use by the Qt Quick`

Status: validated.

Validation log:

```text
/tmp/gui-qml-staging-buildwalk-logs/014-0b49e9d7e0-graphics-build.log
```

Intermediate checkpoint that built with the same accumulated patch before this
hash:

```text
2b2c35e544 Merge bitcoin-core/gui-qml#34: Add copyright headers to QML files
```

Failures found:

- The recurring `bitcoin.cpp`/CMake patch needed a new context because PR #32
  adds `QmlUtil::GraphicsApi(window)`.
- New compile failure in `src/qml/util.cpp`: Qt 6.4 does not have
  `QSGRendererInterface::Direct3D12`, and `OpenGLRhi` aliases the older
  `OpenGL` enum value, producing a duplicate case.

Fix sources:

- Same recurring fix sources listed for `c25b9968b3`.
- `0ac8e6f137 Merge bitcoin-core/gui-qml#475: Add cmake, qt6, and bitcoin core submodule`
  updates `QmlUtil::GraphicsApi()` to the Qt 6 enum names used by the current
  staging build and guards `Direct3D12` behind Qt 6.6.

Additional patch to amend into `0b49e9d7e0`:

```diff
diff --git a/src/qml/util.cpp b/src/qml/util.cpp
@@
     switch (window->rendererInterface()->graphicsApi()) {
     case QSGRendererInterface::Unknown: return "Unknown";
     case QSGRendererInterface::Software: return "The Qt Quick 2D Renderer";
-    case QSGRendererInterface::OpenGL: return "OpenGL ES 2.0 or higher";
-    case QSGRendererInterface::Direct3D12: return "Direct3D 12";
     case QSGRendererInterface::OpenVG: return "OpenVG via EGL";
 #if (QT_VERSION >= QT_VERSION_CHECK(5, 14, 0))
-    case QSGRendererInterface::OpenGLRhi: return "OpenGL ES 2.0 or higher via a graphics abstraction layer";
-    case QSGRendererInterface::Direct3D11Rhi: return "Direct3D 11 via a graphics abstraction layer";
-    case QSGRendererInterface::VulkanRhi: return "Vulkan 1.0 via a graphics abstraction layer";
-    case QSGRendererInterface::MetalRhi: return "Metal via a graphics abstraction layer";
-    case QSGRendererInterface::NullRhi: return "Null (no output) via a graphics abstraction layer";
+    case QSGRendererInterface::OpenGL: return "OpenGL ES 2.0 or higher via a graphics abstraction layer";
+    case QSGRendererInterface::Direct3D11: return "Direct3D 11 via a graphics abstraction layer";
+    case QSGRendererInterface::Vulkan: return "Vulkan 1.0 via a graphics abstraction layer";
+    case QSGRendererInterface::Metal: return "Metal via a graphics abstraction layer";
+    case QSGRendererInterface::Null: return "Null (no output) via a graphics abstraction layer";
+#endif
+#if (QT_VERSION >= QT_VERSION_CHECK(6, 6, 0))
+    case QSGRendererInterface::Direct3D12: return "Direct3D 12 via a graphics abstraction layer";
 #endif
```

The full validated accumulated patch for this checkpoint was saved during the
walk as:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-014-0b49e9d7e0.patch
```

## `49c822db14` `Merge bitcoin-core/gui-qml#44: Do not swallow QML error messages`

Status: validated.

Validation log:

```text
/tmp/gui-qml-staging-buildwalk-logs/016-49c822db14-logging-build.log
```

Intermediate checkpoint that built with the accumulated patch before this hash:

```text
ab098f42ab Merge bitcoin-core/gui-qml#31: Add BlockCounter QML component which handles NotifyBlockTip signal
```

Failures found:

- The recurring patch needed a new context because PR #44 introduces
  `DebugMessageHandler`.
- New compile failure in `src/qml/bitcoin.cpp`: `LogPrint` and `LogPrintf` are
  no longer available in the current logging API.

Fix sources:

- Same recurring fix sources listed for `c25b9968b3`.
- `0ac8e6f137 Merge bitcoin-core/gui-qml#475: Add cmake, qt6, and bitcoin core submodule`
  updates `LogPrint(BCLog::QT, ...)` to `LogDebug(BCLog::QT, ...)`.
- `25a52764ca qml: adapt UI callbacks to Core v31`
  (`Rebased-From: 36c63267051f96cc7511e0d9488593824b3390ac`) updates the
  remaining `LogPrintf(...)` call to `LogInfo(...)`.

Additional patch to amend into `49c822db14`:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
     Q_UNUSED(context);
     if (type == QtDebugMsg) {
-        LogPrint(BCLog::QT, "GUI: %s\n", msg.toStdString());
+        LogDebug(BCLog::QT, "GUI: %s\n", msg.toStdString());
     } else {
-        LogPrintf("GUI: %s\n", msg.toStdString());
+        LogInfo("GUI: %s\n", msg.toStdString());
     }
 }
```

The full validated accumulated patch for this checkpoint was saved during the
walk as:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-016-49c822db14.patch
```

## `921feb5c76` `Merge bitcoin-core/gui-qml#41: Revert a commit from #5 to avoid merge conflict with bitcoin/bitcoin#22219`

Status: validated.

Validation log:

```text
/tmp/gui-qml-staging-buildwalk-logs/018-921feb5c76-compat-build.log
```

Intermediate checkpoint that built with the accumulated patch before this hash:

```text
8f58cc7810 Merge bitcoin-core/gui-qml#45: qml, build, doc: Allow import QtQuick.Layouts
```

Failures found:

- The accumulated patch needed a new context because PR #41 reworks the early
  initialization block and adds Windows argument handling back into
  `QmlGuiMain`.
- Once `SetupEnvironment()` and `WinCmdLineArgs` are present, the current Core
  split requires `common/system.h`, and `WinCmdLineArgs` is now in namespace
  `common`.

Fix sources:

- `11f5ea3b37 Merge bitcoin-core/gui-qml#359: Sync with the main repo` shows
  the move from `util/system.h` to `common/args.h`/`common/system.h` and
  `common::WinCmdLineArgs`.
- Same recurring fix sources listed for `49c822db14`.

Additional patch shape for this checkpoint:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-#include <util/system.h>
+#include <common/args.h>
+#include <common/system.h>
@@
 #ifdef WIN32
-    util::WinCmdLineArgs winArgs;
+    common::WinCmdLineArgs winArgs;
     std::tie(argc, argv) = winArgs.get();
 #endif // WIN32
```

The full validated accumulated patch for this checkpoint was saved during the
walk as:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-018-921feb5c76.patch
```

## `128838c6ba` `Merge bitcoin-core/gui-qml#48: Implement #22219 changes in the qml/bitcoin.cpp`

Status: validated.

Validation log:

```text
/tmp/gui-qml-staging-buildwalk-logs/019-128838c6ba-guinit-build.log
```

Failures found:

- The accumulated patch needed a new context because PR #48 introduces
  `interfaces::MakeNodeInit`.
- Link failure: `undefined reference to interfaces::MakeNodeInit(...)`. The
  staging `bitcoin-qml` target links the GUI init object, so this historical
  node-init call cannot link in the integrated staging build.

Fix sources:

- `a4e3568657 Merge bitcoin-core/gui-qml#72: Sync with the main repo` converts
  the QML startup path from `MakeNodeInit` to `MakeGuiInit`.
- Same recurring fix sources listed for `921feb5c76`.

Additional patch shape for this checkpoint:

```diff
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
@@
-    node::NodeContext node_context;
-    int unused_exit_status;
-    std::unique_ptr<interfaces::Init> init = interfaces::MakeNodeInit(node_context, argc, argv, unused_exit_status);
+    std::unique_ptr<interfaces::Init> init = interfaces::MakeGuiInit(argc, argv);
@@
-    node_context.args = &gArgs;
     SetupServerArgs(gArgs);
```

The full validated accumulated patch for this checkpoint was saved during the
walk as:

```text
/tmp/gui-qml-staging-buildwalk-logs/fix-through-019-128838c6ba.patch
```

Failures found:

- Same API/CMake failures as `5071083ab5`, in the newer initialization-error
  handling shape.
- `ArgsManager::InitSettings` no longer exists in current Core. The current
  replacement is `ReadSettingsFile(&errors)`.
- `MakeUnorderedList` now lives in namespace `util`.

Fix sources:

- Same API/CMake fix sources listed for `238b13c76c`.
- `25a52764ca qml: adapt UI callbacks to Core v31` for the no-caption
  `InitErrorMessageBox` callback.
- Current `src/common/args.h` declares `ReadSettingsFile`.
- Current `src/util/string.h` exposes `util::MakeUnorderedList`.

Patch to amend into `c25b9968b3`:

```diff
diff --git a/src/qml/CMakeLists.txt b/src/qml/CMakeLists.txt
index 727ca78a32..1d23ecfb0b 100644
--- a/src/qml/CMakeLists.txt
+++ b/src/qml/CMakeLists.txt
@@ -4,15 +4,32 @@

 set(CMAKE_AUTOMOC ON)

-add_library(bitcoinqml STATIC
-  bitcoin.cpp
+option(ENABLE_TEST_AUTOMATION "Enable test automation bridge for QML UI testing" OFF)
+
+set(QML_QRC "${CMAKE_CURRENT_SOURCE_DIR}/bitcoin_qml.qrc")
+qt6_add_resources(QML_QRC_CPP ${QML_QRC})
+
+file(GLOB_RECURSE QML_SOURCES
+  "${CMAKE_CURRENT_SOURCE_DIR}/*.cpp"
+  "${CMAKE_CURRENT_SOURCE_DIR}/*.h"
 )
+list(FILTER QML_SOURCES EXCLUDE REGEX "/main\\.cpp$")
+list(FILTER QML_SOURCES EXCLUDE REGEX "/androidnotifier\\.(cpp|h)$")
+if(NOT ENABLE_TEST_AUTOMATION)
+  list(FILTER QML_SOURCES EXCLUDE REGEX "/test/")
+endif()
+list(APPEND QML_SOURCES ${QML_QRC_CPP})
+
+add_library(bitcoinqml STATIC ${QML_SOURCES})
@@
 target_compile_definitions(bitcoinqml
   PUBLIC
     QT_NO_KEYWORDS
     QT_USE_QSTRINGBUILDER
 )
+if(ENABLE_TEST_AUTOMATION)
+  target_compile_definitions(bitcoinqml PUBLIC ENABLE_TEST_AUTOMATION)
+endif()
@@
 target_link_libraries(bitcoinqml
   PUBLIC
     core_interface
     bitcoin_node
+    univalue
+    Boost::headers
+    $<TARGET_NAME_IF_EXISTS:QRencode::QRencode>
     Qt6::Qml
-    Qt6::Widgets
     Qt6::Quick
+    Qt6::QuickControls2
+    Qt6::Network
+    Qt6::Widgets
 )
diff --git a/src/qml/bitcoin.cpp b/src/qml/bitcoin.cpp
index c2eeba72b7..02c7abad18 100644
--- a/src/qml/bitcoin.cpp
+++ b/src/qml/bitcoin.cpp
@@ -7,15 +7,15 @@
 #include <init.h>
 #include <interfaces/node.h>
 #include <node/context.h>
-#include <node/ui_interface.h>
+#include <node/interface_ui.h>
 #include <noui.h>
 #include <qml/nodemodel.h>
 #include <qt/guiconstants.h>
 #include <qt/initexecutor.h>
-#include <util/system.h>
+#include <common/args.h>
 #include <util/translation.h>

-#include <boost/signals2/connection.hpp>
+#include <btcsignals.h>
@@
 bool InitErrorMessageBox(
     const bilingual_str& message,
-    [[maybe_unused]] const std::string& caption,
     [[maybe_unused]] unsigned int style)
@@
-    NodeContext node_context;
+    node::NodeContext node_context;
@@
-        InitError(strprintf(Untranslated("Cannot parse command line arguments: %s\n"), error));
+        InitError(Untranslated(strprintf("Cannot parse command line arguments: %s\n", error)));
@@
-    if (!CheckDataDirOption()) {
-        InitError(strprintf(Untranslated("Specified data directory \"%s\" does not exist.\n"), gArgs.GetArg("-datadir", "")));
+    if (!CheckDataDirOption(gArgs)) {
+        InitError(Untranslated(strprintf("Specified data directory \"%s\" does not exist.\n", gArgs.GetArg("-datadir", ""))));
@@
-        InitError(strprintf(Untranslated("Cannot parse configuration file: %s\n"), error));
+        InitError(Untranslated(strprintf("Cannot parse configuration file: %s\n", error)));
@@
-        SelectParams(gArgs.GetChainName());
+        SelectParams(gArgs.GetChainType());
@@
-    if (!gArgs.InitSettings(error)) {
-        InitError(Untranslated(error));
+    std::vector<std::string> errors;
+    if (!gArgs.ReadSettingsFile(&errors)) {
+        InitError(Untranslated(strprintf("Failed loading settings file:\n%s\n", util::MakeUnorderedList(errors))));
         return EXIT_FAILURE;
     }
@@
-    std::unique_ptr<interfaces::Node> node = interfaces::MakeNode(&node_context);
+    std::unique_ptr<interfaces::Node> node = interfaces::MakeNode(node_context);
```
