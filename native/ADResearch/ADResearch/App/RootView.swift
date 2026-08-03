import SwiftUI

/// 根视图：启动态 → 已登录 Shell / 登录页。
struct RootView: View {
    @Environment(AuthStore.self) private var authStore

    var body: some View {
        Group {
            if !authStore.hasRestoredSession {
                launchView
            } else if authStore.isAuthenticated {
                PlatformShell()
                    .transition(.opacity)
            } else {
                LoginView()
                    .transition(.opacity.combined(with: .scale(scale: 0.98)))
            }
        }
        .animation(AppTheme.Motion.standard, value: authStore.isAuthenticated)
        .animation(AppTheme.Motion.fade, value: authStore.hasRestoredSession)
        .task {
            await authStore.bootstrapSessionIfNeeded()
        }
    }

    /// 会话恢复中的启动态（品牌图标 + 呼吸，不用裸 spinner）
    private var launchView: some View {
        VStack(spacing: AppTheme.Spacing.lg) {
            Image(systemName: "chart.line.uptrend.xyaxis.circle.fill")
                .font(.system(size: 64))
                .foregroundStyle(AppTheme.Colors.accent)
                .symbolRenderingMode(.hierarchical)
            Text("AlloyResearch")
                .font(AppTheme.Typography.pageTitle)
                .foregroundStyle(AppTheme.Colors.textPrimary)
            ProgressView()
                .controlSize(.small)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppTheme.Colors.background)
    }
}
