import SwiftUI

struct ChangePasswordView: View {
    @StateObject private var viewModel = ChangePasswordViewModel()
    @FocusState private var focusedField: Field?

    enum Field { case oldPassword, newPassword, confirmPassword }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                VStack(spacing: 12) {
                    Image(systemName: "lock.shield.fill")
                        .font(.system(size: 44))
                        .foregroundColor(.accent)
                        .padding(22)
                        .background(
                            RoundedRectangle(cornerRadius: 16)
                                .fill(Color.accentDim)
                        )

                    Text("首次登录，请修改密码")
                        .font(.textH1)
                        .foregroundColor(.textPrimary)
                        .kerning(-0.03)

                    Text("为保障账号安全，修改密码后才能继续使用")
                        .font(.textBody)
                        .foregroundColor(.textTertiary)
                        .multilineTextAlignment(.center)
                }
                .padding(.top, 64)

                VStack(spacing: 16) {
                    HStack(spacing: 12) {
                        Image(systemName: "lock.fill")
                            .foregroundColor(.textTertiary)
                        SecureField("旧密码", text: $viewModel.oldPassword)
                            .textContentType(.password)
                            .focused($focusedField, equals: .oldPassword)
                            .submitLabel(.next)
                    }
                    .padding(14)
                    .background(Color.bgInput)
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.borderDefault)
                    )

                    HStack(spacing: 12) {
                        Image(systemName: "key.fill")
                            .foregroundColor(.textTertiary)
                        SecureField("新密码", text: $viewModel.newPassword)
                            .textContentType(.newPassword)
                            .focused($focusedField, equals: .newPassword)
                            .submitLabel(.next)
                    }
                    .padding(14)
                    .background(Color.bgInput)
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.borderDefault)
                    )

                    HStack(spacing: 12) {
                        Image(systemName: "checkmark.shield.fill")
                            .foregroundColor(.textTertiary)
                        SecureField("确认新密码", text: $viewModel.confirmPassword)
                            .textContentType(.newPassword)
                            .focused($focusedField, equals: .confirmPassword)
                            .submitLabel(.go)
                    }
                    .padding(14)
                    .background(Color.bgInput)
                    .cornerRadius(8)
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.borderDefault)
                    )
                }
                .padding(.top, 40)
                .onSubmit {
                    switch focusedField {
                    case .oldPassword:
                        focusedField = .newPassword
                    case .newPassword:
                        focusedField = .confirmPassword
                    default:
                        Task { await viewModel.changePassword() }
                    }
                }

                Text("12–64 位，需包含英文字母和数字")
                    .font(.textSmall)
                    .foregroundColor(.textTertiary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.top, 12)

                if let error = viewModel.errorMessage {
                    Text(error)
                        .font(.textSmall)
                        .foregroundColor(.colorRise)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 12)
                }

                Button(action: { Task { await viewModel.changePassword() } }) {
                    Group {
                        if viewModel.isLoading {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: .black))
                        } else {
                            Text("修改密码并登录")
                                .fontWeight(.medium)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(viewModel.hasRequiredFields ? Color.accent : Color.textMuted)
                    .foregroundColor(viewModel.hasRequiredFields ? .black : .textSecondary)
                    .cornerRadius(10)
                }
                .disabled(!viewModel.hasRequiredFields || viewModel.isLoading)
                .padding(.top, 24)

                Button(action: { Task { await AuthManager.shared.logout() } }) {
                    Text("退出登录")
                        .font(.textBody)
                        .foregroundColor(.textSecondary)
                }
                .disabled(viewModel.isLoading)
                .padding(.top, 20)
                .padding(.bottom, 32)
            }
            .padding(.horizontal, 32)
        }
        .background(Color.bgBase.ignoresSafeArea())
        .onTapGesture { focusedField = nil }
    }
}

#Preview {
    ChangePasswordView()
        .preferredColorScheme(.dark)
}
