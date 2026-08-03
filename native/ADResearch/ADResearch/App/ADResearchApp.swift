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
    }
}

#if os(macOS)
/// macOS 菜单栏命令：⌘1-5 切换主导航（对齐系统 App「股市/播客」的侧栏快捷键）。
struct NavigationCommands: Commands {
    let appState: AppState

    var body: some Commands {
        CommandMenu("导航") {
            ForEach(Array(AppSection.primary.enumerated()), id: \.element) { index, section in
                Button(section.title) {
                    appState.selectedSection = section
                }
                .keyboardShortcut(KeyEquivalent(Character("\(index + 1)")), modifiers: .command)
            }
            Divider()
            ForEach(AppSection.secondary) { section in
                Button(section.title) {
                    appState.selectedSection = section
                }
            }
        }
    }
}
#endif
