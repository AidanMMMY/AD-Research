import SwiftUI

struct LoginView: View {
    @StateObject private var viewModel = LoginViewModel()
    @FocusState private var focusedField: Field?

    enum Field { case username, password }

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            // Logo
            VStack(spacing: 12) {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(.system(size: 48))
                    .foregroundColor(.accent)
                    .padding(24)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(Color.accentDim)
                    )

                Text("投研平台")
                    .font(.textH1)
                    .foregroundColor(.textPrimary)
                    .kerning(-0.03)

                Text("智能投研，数据驱动决策")
                    .font(.textBody)
                    .foregroundColor(.textTertiary)
            }

            Spacer().frame(height: 48)

            // Fields
            VStack(spacing: 16) {
                HStack(spacing: 12) {
                    Image(systemName: "person.fill")
                        .foregroundColor(.textTertiary)
                    TextField("用户名", text: $viewModel.username)
                        .textContentType(.username)
                        .autocapitalization(.none)
                        .focused($focusedField, equals: .username)
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
                    Image(systemName: "lock.fill")
                        .foregroundColor(.textTertiary)
                    SecureField("密码", text: $viewModel.password)
                        .textContentType(.password)
                        .focused($focusedField, equals: .password)
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
            .onSubmit {
                if focusedField == .username {
                    focusedField = .password
                } else if viewModel.isValid {
                    Task { await viewModel.login() }
                }
            }

            if let error = viewModel.errorMessage {
                Text(error)
                    .font(.textSmall)
                    .foregroundColor(.colorRise)
                    .padding(.top, 12)
            }

            // Login button
            Button(action: { Task { await viewModel.login() } }) {
                Group {
                    if viewModel.isLoading {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: .black))
                    } else {
                        Text("登录")
                            .fontWeight(.medium)
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(viewModel.isValid ? Color.accent : Color.textMuted)
                .foregroundColor(viewModel.isValid ? .black : .textSecondary)
                .cornerRadius(10)
            }
            .disabled(!viewModel.isValid || viewModel.isLoading)
            .padding(.top, 24)

            Spacer()

            Text("没有账号？请联系管理员")
                .font(.textSmall)
                .foregroundColor(.textTertiary)
                .padding(.bottom, 32)
        }
        .padding(.horizontal, 32)
        .background(Color.bgBase.ignoresSafeArea())
        .onTapGesture { focusedField = nil }
    }
}

#Preview {
    LoginView()
        .preferredColorScheme(.dark)
}
