import SwiftUI

/// 我的（设置）：账户信息 + API 配置 + 登出。
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
            logoutSection
        }
        .confirmationDialog("确认退出登录？", isPresented: $showLogoutConfirmation, titleVisibility: .visible) {
            Button("退出登录", role: .destructive) {
                Task { await authStore.logout() }
            }
            Button("取消", role: .cancel) {}
        }
    }
    #endif

    #if os(macOS)
    private var macForm: some View {
        Form {
            accountSection
            apiSection
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
        }
    }
    #endif

    private var accountSection: some View {
        Section("账户") {
            LabeledContent("用户名", value: authStore.currentUser?.username ?? "—")
            LabeledContent("角色") {
                Text(roleLabel(authStore.currentUser?.role))
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
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

    private func roleLabel(_ role: String?) -> String {
        switch role {
        case "admin": return "管理员"
        case "user": return "用户"
        default: return "—"
        }
    }
}
