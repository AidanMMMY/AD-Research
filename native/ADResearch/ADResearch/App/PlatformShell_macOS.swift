#if os(macOS)
import SwiftUI

/// macOS 平台外壳：**三栏** NavigationSplitView（侧栏 + 列表 + 详情）。
///
/// - 侧栏两组：主导航（⌘1-5）+ 功能模块（⌥⌘，见 ``NavigationCommands``）
/// - 内容列：当前分区的根视图（列表），切换分区经 ``AppState/selectSection(_:)``
///   清空 detailPath，避免详情栈残留
/// - 详情列：独立 NavigationStack（detailPath），空栈时显示占位页；
///   列表点击经 ``AppState/navigate(to:route:)`` 推入，⌘[ 返回上一层
/// - 多窗口就绪：WindowGroup 原生支持 ⌘N 新窗口，各窗口状态相互独立
struct PlatformShell: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        @Bindable var state = appState
        NavigationSplitView {
            List(selection: sectionBinding) {
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
        } content: {
            FeatureRouter.rootView(for: appState.selectedSection)
                .id(appState.selectedSection) // 切换分区时重建列表视图
                .navigationTitle(appState.selectedSection.title)
                .navigationSplitViewColumnWidth(min: 340, ideal: 400, max: 520)
        } detail: {
            NavigationStack(path: $state.detailPath) {
                detailPlaceholder
                    .navigationDestination(for: AppRoute.self) { route in
                        FeatureRouter.destination(for: route)
                    }
            }
        }
        .navigationSplitViewStyle(.balanced)
        .frame(minWidth: 1120, minHeight: 640)
        .background(backShortcutButton)
        .sheet(isPresented: $state.showGlobalSearch) {
            GlobalSearchView()
                .environment(appState)
        }
        .sheet(isPresented: $state.showShortcutsCheatSheet) {
            ShortcutsCheatSheetView()
        }
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

    /// 详情列空态：引导从内容列选择（分区图标随当前分区变化）
    private var detailPlaceholder: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: appState.selectedSection.systemImage)
                .font(.system(size: 44))
                .foregroundStyle(AppTheme.Colors.textMuted.opacity(0.6))
                .symbolRenderingMode(.hierarchical)
            Text("从列表选择一项查看详情")
                .font(AppTheme.Typography.callout)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            Text("⌘K 全局搜索 · ⌘[ 返回")
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppTheme.Colors.background)
    }

    /// 侧栏选择绑定：写入时走 selectSection，切换分区自动清空 detailPath 残留
    private var sectionBinding: Binding<AppSection> {
        Binding(
            get: { appState.selectedSection },
            set: { appState.selectSection($0) }
        )
    }

    /// ⌘[ 返回上一层详情。隐藏按钮承载快捷键（opacity(0) 保留在视图树中，
    /// 快捷键仍然生效；.hidden() 会把节点移出视图树导致快捷键失效，不能用）。
    /// 详情栈为空时 disable，避免吞掉其他场景的 ⌘[。
    private var backShortcutButton: some View {
        Button {
            if !appState.detailPath.isEmpty {
                appState.detailPath.removeLast()
            }
        } label: {
            EmptyView()
        }
        .keyboardShortcut("[", modifiers: .command)
        .disabled(appState.detailPath.isEmpty)
        .opacity(0)
        .accessibilityHidden(true)
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
