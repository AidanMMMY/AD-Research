#if os(iOS)
import SwiftUI

/// iOS 平台外壳：五个主 tab（首页/资讯/行情/研报/更多），
/// 每个 tab 独立 NavigationStack，路由经 ``AppRoute`` 登记。
///
/// 第 5 个 tab 是「更多」入口页（``MoreTabView``）：5-tab 结构放不下
/// 组合/研究笔记/学习中心等二级模块，统一从这里经 AppRoute.section 推送；
/// 账户与设置（SettingsView）也由此进入。tag 仍用 .settings，导航逻辑不变。
struct PlatformShell: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        @Bindable var state = appState
        TabView(selection: $state.selectedSection) {
            ForEach(AppSection.primary) { section in
                NavigationStack(path: state.pathBinding(for: section)) {
                    tabRoot(for: section)
                        .navigationTitle(navigationTitle(for: section))
                        .navigationBarTitleDisplayMode(.large)
                        .navigationDestination(for: AppRoute.self) { route in
                            FeatureRouter.destination(for: route)
                        }
                }
                .tabItem {
                    tabLabel(for: section)
                }
                .tag(section)
            }
        }
        .tint(AppTheme.Colors.accent)
        .onChange(of: appState.selectedSection) { _, _ in
            Haptics.selection()
        }
    }

    @ViewBuilder
    private func tabRoot(for section: AppSection) -> some View {
        if section == .settings {
            MoreTabView()
        } else {
            FeatureRouter.rootView(for: section)
        }
    }

    private func navigationTitle(for section: AppSection) -> String {
        section == .settings ? "更多" : section.title
    }

    @ViewBuilder
    private func tabLabel(for section: AppSection) -> some View {
        if section == .settings {
            Label("更多", systemImage: "ellipsis.circle")
        } else {
            Label(section.title, systemImage: section.systemImage)
        }
    }
}

/// iOS「更多」页：二级功能模块入口（标的/宏观/情绪/板块/组合/研究笔记/学习）
/// + 账户与设置入口。复用现有路由登记表，不新增 route case、不改 Features。
private struct MoreTabView: View {
    var body: some View {
        List {
            Section("功能模块") {
                ForEach(AppSection.secondary) { section in
                    NavigationLink(value: AppRoute.section(section)) {
                        Label(section.title, systemImage: section.systemImage)
                    }
                }
            }
            Section("账户") {
                NavigationLink(value: AppRoute.section(.settings)) {
                    Label("我的与设置", systemImage: AppSection.settings.systemImage)
                }
            }
        }
    }
}

#Preview {
    PlatformShell()
        .environment(AppState())
        .environment(AuthStore.shared)
}
#endif
