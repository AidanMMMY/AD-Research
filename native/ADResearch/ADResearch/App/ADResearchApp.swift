import SwiftUI

/// 应用入口。
@main
struct ADResearchApp: App {
    @State private var appState = AppState()
    @State private var authStore = AuthStore.shared

    var body: some Scene {
        WindowGroup {
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
    }
}
#endif
