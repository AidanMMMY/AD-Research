#if os(macOS)
import SwiftUI

/// macOS 平台外壳：NavigationSplitView 侧栏 + 详情列。
///
/// - 侧栏两组：主导航（⌘1-5，见 ``NavigationCommands``）+ 功能模块
/// - 详情列共享一条 NavigationStack 路径
/// - 多窗口就绪：WindowGroup 原生支持 ⌘N 新窗口，各窗口状态相互独立
struct PlatformShell: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        @Bindable var state = appState
        NavigationSplitView {
            List(selection: $state.selectedSection) {
                Section("主导航") {
                    ForEach(AppSection.primary) { section in
                        Label(section.title, systemImage: section.systemImage)
                            .tag(section)
                    }
                }
                Section("功能模块") {
                    ForEach(AppSection.secondary) { section in
                        Label(section.title, systemImage: section.systemImage)
                            .tag(section)
                    }
                }
            }
            .listStyle(.sidebar)
            .navigationSplitViewColumnWidth(min: 200, ideal: 220, max: 260)
        } detail: {
            NavigationStack(path: $state.detailPath) {
                FeatureRouter.rootView(for: appState.selectedSection)
                    .id(appState.selectedSection) // 切换分区时重建详情视图
                    .navigationTitle(appState.selectedSection.title)
                    .navigationDestination(for: AppRoute.self) { route in
                        FeatureRouter.destination(for: route)
                    }
            }
        }
        .navigationSplitViewStyle(.balanced)
        .frame(minWidth: 960, minHeight: 600)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    NotificationCenter.default.post(name: .adRefreshRequested, object: nil)
                } label: {
                    Label("刷新", systemImage: "arrow.clockwise")
                }
                .keyboardShortcut("r", modifiers: .command)
                .help("刷新当前页面数据（⌘R）")
            }
        }
    }
}

/// 页面刷新广播：各 ViewModel 按需监听（Dashboard 已接入）。
extension Notification.Name {
    static let adRefreshRequested = Notification.Name("adRefreshRequested")
}

#Preview {
    PlatformShell()
        .environment(AppState())
        .environment(AuthStore.shared)
}
#endif
