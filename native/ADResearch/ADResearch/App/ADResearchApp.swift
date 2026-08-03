import SwiftUI

/// 应用入口。
@main
struct ADResearchApp: App {
    @State private var appState = AppState()
    @State private var authStore = AuthStore.shared
    #if os(macOS)
    @State private var menuBarModel = MenuBarViewModel()
    #endif

    var body: some Scene {
        WindowGroup(id: "main") {
            RootView()
                .environment(appState)
                .environment(authStore)
                #if os(iOS)
                .tint(AppTheme.Colors.accent)
                #endif
        }
        #if os(macOS)
        .defaultSize(width: 1240, height: 820)
        .commands {
            NavigationCommands(appState: appState)
        }
        #endif

        #if os(macOS)
        // ⌘, 设置窗口（Settings scene 仅 macOS 有效；iOS 走「更多」tab 内的设置入口）。
        // 内容复用 Features/Settings/SettingsView（账户/API 信息/关于/登出，Form + .grouped），只读不改。
        Settings {
            SettingsView()
                .environment(authStore)
        }

        // 菜单栏行情 widget：label 常驻（图标+标普涨跌幅），点开五大指数+快捷操作
        MenuBarExtra {
            MenuBarView(viewModel: menuBarModel)
        } label: {
            MenuBarLabel(model: menuBarModel)
        }
        .menuBarExtraStyle(.window)
        #endif
    }
}

#if os(macOS)
/// macOS 菜单栏命令：⌘1-5 切换主导航、⌥⌘1-7 切换二级模块
/// （对齐系统 App「股市/播客」的侧栏快捷键）。
struct NavigationCommands: Commands {
    let appState: AppState

    var body: some Commands {
        CommandMenu("导航") {
            Button("全局搜索") {
                appState.showGlobalSearch = true
            }
            .keyboardShortcut("k", modifiers: .command)
            Divider()
            ForEach(Array(AppSection.primary.enumerated()), id: \.element) { index, section in
                Button(section.title) {
                    appState.selectSection(section)
                }
                .keyboardShortcut(KeyEquivalent(Character("\(index + 1)")), modifiers: .command)
            }
            Divider()
            ForEach(Array(AppSection.secondary.enumerated()), id: \.element) { index, section in
                Button(section.title) {
                    appState.selectSection(section)
                }
                .keyboardShortcut(KeyEquivalent(Character("\(index + 1)")), modifiers: [.option, .command])
            }
        }

        // 视图菜单：刷新 + 侧栏/详情列显隐（与系统快捷键一致）
        CommandMenu("视图") {
            Button("刷新") {
                NotificationCenter.default.post(name: .adRefreshRequested, object: nil)
            }
            .keyboardShortcut("r", modifiers: .command)
            Divider()
            Button("切换侧栏") {
                NSApp.keyWindow?.firstResponder?.tryToPerform(
                    #selector(NSSplitViewController.toggleSidebar(_:)), with: nil
                )
            }
            .keyboardShortcut("s", modifiers: [.command, .control])
        }

        // 帮助菜单：快捷键速览（菜单栏帮助搜索可索引到）
        CommandMenu("帮助") {
            Button("快捷键速览") {
                appState.showShortcutsCheatSheet = true
            }
        }
    }
}

/// 快捷键速览弹窗（帮助菜单唤起）
struct ShortcutsCheatSheetView: View {
    @Environment(\.dismiss) private var dismiss

    private static let rows: [(String, String)] = [
        ("⌘K", "全局搜索"),
        ("⌘R", "刷新当前页"),
        ("⌘[", "返回上一层详情"),
        ("⌘1 – ⌘5", "主导航切换"),
        ("⌥⌘1 – ⌥⌘8", "功能模块切换"),
        ("⌃⌘S", "切换侧栏"),
        ("⌘,", "设置"),
        ("⌘N", "新窗口"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Text("快捷键速览")
                .font(AppTheme.Typography.title3)
                .foregroundStyle(AppTheme.Colors.textPrimary)
            VStack(spacing: 0) {
                ForEach(Self.rows, id: \.0) { keys, action in
                    HStack {
                        Text(keys)
                            .font(AppTheme.Typography.numericCallout)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .frame(width: 110, alignment: .leading)
                        Text(action)
                            .font(AppTheme.Typography.callout)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                        Spacer()
                    }
                    .padding(.vertical, AppTheme.Spacing.xs)
                    if keys != Self.rows.last?.0 {
                        Divider().opacity(0.5)
                    }
                }
            }
            Button("关闭") { dismiss() }
                .keyboardShortcut(.defaultAction)
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .padding(AppTheme.Spacing.lg)
        .frame(width: 340)
        .background(AppTheme.Colors.background)
    }
}
#endif
