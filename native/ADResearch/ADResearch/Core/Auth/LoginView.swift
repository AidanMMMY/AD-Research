import SwiftUI

/// 登录页（两平台各自地道布局）：
/// - iOS：顶部品牌区 + 圆角卡片表单，键盘避让，全宽主按钮
/// - macOS：居中固定宽面板（对齐系统 App 的登录/设置面板风格）
struct LoginView: View {
    @Environment(AuthStore.self) private var authStore

    @State private var username = ""
    @State private var password = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    private var canSubmit: Bool {
        !username.trimmingCharacters(in: .whitespaces).isEmpty && !password.isEmpty && !isSubmitting
    }

    var body: some View {
        #if os(iOS)
        iosBody
        #else
        macBody
        #endif
    }

    // MARK: - iOS：品牌区 + 卡片表单

    #if os(iOS)
    private var iosBody: some View {
        ScrollView {
            VStack(spacing: AppTheme.Spacing.xxl) {
                Spacer(minLength: AppTheme.Spacing.section)
                brandHeader
                formCard
                Spacer(minLength: AppTheme.Spacing.section)
            }
            .padding(.horizontal, AppTheme.Spacing.xl)
        }
        .background(AppTheme.Colors.background)
        .scrollDismissesKeyboard(.interactively)
    }
    #endif

    // MARK: - macOS：居中面板

    #if os(macOS)
    private var macBody: some View {
        VStack(spacing: AppTheme.Spacing.xxl) {
            Spacer()
            brandHeader
            formCard
                .frame(width: 380)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppTheme.Colors.background)
    }
    #endif

    // MARK: - 共享片段

    private var brandHeader: some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "chart.line.uptrend.xyaxis.circle.fill")
                .font(.system(size: 56))
                .foregroundStyle(AppTheme.Colors.accent)
                .symbolRenderingMode(.hierarchical)
            Text("AD 研究")
                .font(AppTheme.Typography.largeTitle)
                .foregroundStyle(AppTheme.Colors.textPrimary)
            Text("Alloy Research 投资研究平台")
                .font(AppTheme.Typography.callout)
                .foregroundStyle(AppTheme.Colors.textMuted)
        }
    }

    private var formCard: some View {
        ADCard {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                Text("登录")
                    .font(AppTheme.Typography.pageTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)

                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    labeledField(title: "用户名") {
                        TextField("请输入用户名", text: $username)
                            .textContentType(.username)
                            #if os(iOS)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            #endif
                    }
                    labeledField(title: "密码") {
                        SecureField("请输入密码", text: $password)
                            .textContentType(.password)
                    }
                }

                if let errorMessage {
                    Text(errorMessage)
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.error)
                        .transition(.opacity.combined(with: .move(edge: .top)))
                }

                Button {
                    submit()
                } label: {
                    Group {
                        if isSubmitting {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Text("登 录")
                                .font(.headline)
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .padding(.vertical, AppTheme.Spacing.xs)
                }
                .buttonStyle(.borderedProminent)
                .tint(AppTheme.Colors.accent)
                .controlSize(.large)
                .disabled(!canSubmit)
                #if os(macOS)
                .keyboardShortcut(.defaultAction)
                #endif
            }
        }
    }

    private func labeledField<Content: View>(
        title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            Text(title)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            content()
                .textFieldStyle(.plain)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm)
                .background(
                    RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                        .fill(AppTheme.Colors.surface)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                        .strokeBorder(AppTheme.Colors.border, lineWidth: 0.5)
                )
        }
    }

    // MARK: - 提交

    private func submit() {
        guard canSubmit else { return }
        isSubmitting = true
        errorMessage = nil
        Haptics.selection()
        Task {
            do {
                _ = try await authStore.login(
                    username: username.trimmingCharacters(in: .whitespaces),
                    password: password
                )
                Haptics.notify(success: true)
            } catch let error as APIError {
                withAnimation(AppTheme.Motion.standard) {
                    errorMessage = error.userMessage
                }
                Haptics.notify(success: false)
            } catch {
                withAnimation(AppTheme.Motion.standard) {
                    errorMessage = "登录失败，请稍后重试"
                }
                Haptics.notify(success: false)
            }
            isSubmitting = false
        }
    }
}

#Preview {
    LoginView()
        .environment(AuthStore.shared)
}
