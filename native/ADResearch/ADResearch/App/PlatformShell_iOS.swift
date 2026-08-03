#if os(iOS)
import SwiftUI

/// iOS 平台外壳：五个主 tab（首页/资讯/行情/研报/我的），
/// 每个 tab 独立 NavigationStack，路由经 ``AppRoute`` 登记。
struct PlatformShell: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        @Bindable var state = appState
        TabView(selection: $state.selectedSection) {
            ForEach(AppSection.primary) { section in
                NavigationStack(path: state.pathBinding(for: section)) {
                    FeatureRouter.rootView(for: section)
                        .navigationTitle(section.title)
                        #if os(iOS)
                        .navigationBarTitleDisplayMode(.large)
                        #endif
                        .navigationDestination(for: AppRoute.self) { route in
                            FeatureRouter.destination(for: route)
                        }
                }
                .tabItem {
                    Label(section.title, systemImage: section.systemImage)
                }
                .tag(section)
            }
        }
        .tint(AppTheme.Colors.accent)
        .onChange(of: appState.selectedSection) { _, _ in
            Haptics.selection()
        }
    }
}

#Preview {
    PlatformShell()
        .environment(AppState())
        .environment(AuthStore.shared)
}
#endif
