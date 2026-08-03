import SwiftUI

/// 我的（设置）：用户信息卡 + API 配置 + 关于（版本）+ 登出（带确认）。
struct SettingsView: View {
    @Environment(AuthStore.self) private var authStore
    @State private var showLogoutConfirmation = false

    var body: some View {
        #if os(iOS)
        iosForm
        #else
        macForm
        #endif
    }

    #if os(iOS)
    private var iosForm: some View {
        Form {
            accountSection
            apiSection
            aboutSection
            logoutSection
        }
        .confirmationDialog("确认退出登录？", isPresented: $showLogoutConfirmation, titleVisibility: .visible) {
            Button("退出登录", role: .destructive) {
                Task { await authStore.logout() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("退出后需要重新登录才能继续使用")
        }
    }
    #endif

    #if os(macOS)
    private var macForm: some View {
        Form {
            accountSection
            apiSection
            notificationSection
            aboutSection
            logoutSection
        }
        .formStyle(.grouped)
        .frame(minWidth: 520)
        .padding(AppTheme.Spacing.lg)
        .confirmationDialog("确认退出登录？", isPresented: $showLogoutConfirmation, titleVisibility: .visible) {
            Button("退出登录", role: .destructive) {
                Task { await authStore.logout() }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("退出后需要重新登录才能继续使用")
        }
    }
    #endif

    /// 用户信息卡：头像 + 用户名 + 角色徽标
    private var accountSection: some View {
        Section("账户") {
            HStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: "person.circle.fill")
                    .font(.system(size: 44))
                    .foregroundStyle(AppTheme.Colors.accent)
                    .symbolRenderingMode(.hierarchical)
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text(authStore.currentUser?.username ?? "未同步")
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text(roleLabel(authStore.currentUser?.role))
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.accent)
                        .padding(.horizontal, AppTheme.Spacing.sm)
                        .padding(.vertical, AppTheme.Spacing.xxs)
                        .background(
                            Capsule(style: .continuous).fill(AppTheme.Colors.accentSoft)
                        )
                }
                Spacer()
            }
            .padding(.vertical, AppTheme.Spacing.xs)
        }
    }

    private var apiSection: some View {
        Section("服务") {
            LabeledContent("API 地址") {
                Text(AppConstants.apiBaseURL.host ?? AppConstants.apiBaseURL.absoluteString)
                    .font(AppTheme.Typography.caption.monospaced())
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
        }
    }

    /// 关于：版本号 + 构建号（读 Bundle，缺失时显示占位）
    private var aboutSection: some View {
        Section("关于") {
            LabeledContent("应用", value: "AlloyResearch")
            LabeledContent("版本", value: Self.appVersion)
            LabeledContent("构建号", value: Self.buildNumber)
        }
    }

    #if os(macOS)
    /// 提醒：每日研报本地通知（07:00，平台 06:30 出报后的阅读提醒）
    private var notificationSection: some View {
        Section("提醒") {
            Toggle(
                "每日研报提醒（07:00）",
                isOn: Binding(
                    get: { NotificationManager.shared.isEnabled },
                    set: { NotificationManager.shared.isEnabled = $0 }
                )
            )
            if NotificationManager.shared.authorizationDenied {
                Text("通知权限被拒：请在 系统设置 › 通知 › AlloyResearch 中开启")
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
        }
    }
    #endif

    private var logoutSection: some View {
        Section {
            Button(role: .destructive) {
                showLogoutConfirmation = true
            } label: {
                #if os(iOS)
                HStack {
                    Spacer()
                    Text("退出登录")
                    Spacer()
                }
                #else
                Text("退出登录")
                #endif
            }
        }
    }

    private static var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—"
    }

    private static var buildNumber: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "—"
    }

    private func roleLabel(_ role: String?) -> String {
        switch role {
        case "admin": return "管理员"
        case "user": return "用户"
        default: return "—"
        }
    }
}
