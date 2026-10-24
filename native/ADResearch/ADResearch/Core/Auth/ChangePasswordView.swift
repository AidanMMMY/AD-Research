import SwiftUI

/// 首次登录强制改密页：在 RootView 中替代双平台主 Shell。
struct ChangePasswordView: View {
    @Environment(AuthStore.self) private var authStore

    @State private var oldPassword = ""
    @State private var newPassword = ""
    @State private var confirmPassword = ""
    @State private var isSubmitting = false
    @State private var isLoggingOut = false
    @State private var errorMessage: String?

    @FocusState private var focusedField: Field?
    private enum Field { case oldPassword, newPassword, confirmPassword }

    private var canSubmit: Bool {
        !oldPassword.isEmpty && !newPassword.isEmpty && !confirmPassword.isEmpty &&
        !isSubmitting && !isLoggingOut
    }

    var body: some View {
        ZStack {
            AppTheme.Colors.background.ignoresSafeArea()
            #if os(iOS)
            ScrollView {
                content
                    .padding(.horizontal, AppTheme.Spacing.xl)
                    .padding(.vertical, AppTheme.Spacing.section)
                    .frame(maxWidth: 480)
                    .frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
            #else
            content
                .padding(AppTheme.Spacing.xl)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            #endif
        }
    }

    private var content: some View {
        VStack(spacing: AppTheme.Spacing.section) {
            VStack(spacing: AppTheme.Spacing.md) {
                Image(systemName: "lock.shield")
                    .font(.system(size: 44))
                    .foregroundStyle(AppTheme.Colors.accent)
                    .symbolRenderingMode(.hierarchical)
                Text("首次登录，请修改密码")
                    .font(AppTheme.Typography.pageTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text("为保障账号安全，修改密码后才能继续使用")
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .multilineTextAlignment(.center)
            }

            ADCard {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                        passwordField(title: "旧密码", placeholder: "请输入旧密码", text: $oldPassword)
                            .focused($focusedField, equals: .oldPassword)
                            .onSubmit { focusedField = .newPassword }
                        passwordField(title: "新密码", placeholder: "请输入新密码", text: $newPassword)
                            .focused($focusedField, equals: .newPassword)
                            .onSubmit { focusedField = .confirmPassword }
                        passwordField(title: "确认新密码", placeholder: "请再次输入新密码", text: $confirmPassword)
                            .focused($focusedField, equals: .confirmPassword)
                            .onSubmit(submit)
                    }

                    Text("12–64 位，需包含英文字母和数字")
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)

                    if let errorMessage {
                        Text(errorMessage)
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.error)
                    }

                    Button(action: submit) {
                        Group {
                            if isSubmitting {
                                ProgressView()
                            } else {
                                Text("修改密码并登录")
                            }
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(!canSubmit)
                    #if os(macOS)
                    .keyboardShortcut(.defaultAction)
                    #endif

                    Button("退出登录") {
                        isLoggingOut = true
                        Task {
                            await authStore.logout()
                            isLoggingOut = false
                        }
                    }
                    .buttonStyle(.borderless)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .disabled(isSubmitting || isLoggingOut)
                    .frame(maxWidth: .infinity)
                }
            }
            .frame(maxWidth: 420)
        }
    }

    private func passwordField(
        title: String,
        placeholder: String,
        text: Binding<String>
    ) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            Text(title)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            SecureField(placeholder, text: text)
                .textFieldStyle(.plain)
                .textContentType(.password)
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm + 2)
                .background {
                    RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                        .fill(AppTheme.Colors.surface)
                }
                .overlay {
                    RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                        .strokeBorder(AppTheme.Colors.border, lineWidth: 0.5)
                }
        }
    }

    private func submit() {
        guard canSubmit else { return }
        if let message = PasswordPolicy.validateChange(
            oldPassword: oldPassword,
            newPassword: newPassword,
            confirmation: confirmPassword
        ) {
            errorMessage = message
            Haptics.notify(success: false)
            return
        }

        isSubmitting = true
        errorMessage = nil
        Haptics.selection()
        Task {
            do {
                try await authStore.changePassword(oldPassword: oldPassword, newPassword: newPassword)
                Haptics.notify(success: true)
            } catch let error as APIError {
                errorMessage = error.userMessage
                Haptics.notify(success: false)
            } catch {
                errorMessage = "修改密码失败，请稍后重试"
                Haptics.notify(success: false)
            }
            isSubmitting = false
        }
    }
}

#Preview {
    ChangePasswordView()
        .environment(AuthStore.shared)
}
