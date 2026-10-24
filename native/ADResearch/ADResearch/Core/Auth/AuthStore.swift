import Foundation
import Observation

/// 认证状态仓库（对齐 web 端 ``stores/auth`` 的职责）：
///
/// - ``login`` / ``logout`` / 会话恢复
/// - 令牌持久化到 Keychain，内存态交给 ``APIClient``（对齐 web 的
///   localStorage + axios 拦截器分工）
/// - 会话失效（刷新失败）时由 ``APIClient`` 回调，强制回到登录页
@MainActor
@Observable
final class AuthStore {
    static let shared = AuthStore()

    /// 是否已登录（以本地是否持有令牌为准；``currentUser`` 可能因离线暂缺）
    private(set) var isAuthenticated = false
    /// 当前用户资料（登录响应或 /auth/me 回填）
    private(set) var currentUser: UserProfile?
    /// 是否被后端要求在首次进入主界面前修改密码
    var requiresPasswordChange: Bool {
        currentUser?.mustChangePassword ?? false
    }
    /// 启动时的会话恢复是否已完成（RootView 据此显示启动态）
    private(set) var hasRestoredSession = false

    private init() {}

    /// 注册会话失效回调 + 启动时恢复会话（RootView 的 .task 里调用，幂等）
    func bootstrapSessionIfNeeded() async {
        guard !hasRestoredSession else { return }
        await APIClient.shared.setSessionExpiredHandler { [weak self] in
            Task { @MainActor in
                self?.handleSessionExpired()
            }
        }
        // 后端轮换 refresh_token：刷新成功后把新令牌对写回 Keychain
        await APIClient.shared.setTokensUpdatedHandler { access, refresh in
            KeychainHelper.save(access, account: AppConstants.keychainAccountAccessToken)
            KeychainHelper.save(refresh, account: AppConstants.keychainAccountRefreshToken)
        }
        await restoreSession()
        hasRestoredSession = true
    }

    /// 登录
    @discardableResult
    func login(username: String, password: String) async throws -> UserProfile {
        let endpoint = try Endpoint.authLogin(LoginRequest(username: username, password: password))
        let response = try await APIClient.shared.send(endpoint, as: LoginResponse.self)
        await persist(accessToken: response.accessToken, refreshToken: response.refreshToken)
        currentUser = response.user
        isAuthenticated = true
        return response.user
    }

    /// 首次登录强制改密：成功后后端返回并轮换新的令牌对
    func changePassword(oldPassword: String, newPassword: String) async throws {
        let endpoint = try Endpoint.authChangePassword(
            ChangePasswordRequest(oldPassword: oldPassword, newPassword: newPassword)
        )
        let response = try await APIClient.shared.send(endpoint, as: ChangePasswordResponse.self)
        await persist(accessToken: response.accessToken, refreshToken: response.refreshToken)
        if let user = currentUser {
            currentUser = UserProfile(
                id: user.id,
                username: user.username,
                role: user.role,
                mustChangePassword: false
            )
        }
        isAuthenticated = true
    }

    /// 登出：尽力通知后端，本地状态无条件清空（对齐 web logout 语义）
    func logout() async {
        try? await APIClient.shared.send(.authLogout)
        clearLocalSession()
    }

    /// 从 Keychain 恢复会话，并用 /auth/me 回填用户资料与强制改密状态。
    /// - 401 → 清会话回登录页
    /// - 网络错误 → 保留会话（离线可用，等下次请求再触发刷新/登出）
    private func restoreSession() async {
        guard let access = KeychainHelper.read(account: AppConstants.keychainAccountAccessToken),
              let refresh = KeychainHelper.read(account: AppConstants.keychainAccountRefreshToken) else {
            clearLocalSession()
            return
        }
        await APIClient.shared.setTokens(accessToken: access, refreshToken: refresh)
        do {
            // 在 /auth/me 返回前保持启动态，避免待改密用户短暂进入主 Shell。
            currentUser = try await APIClient.shared.send(.authMe, as: UserProfile.self)
            isAuthenticated = true
        } catch let error as APIError {
            if error == .unauthorized {
                clearLocalSession()
            } else {
                // 其他错误（离线/5xx/解析失败）：保留会话，currentUser 留空
                isAuthenticated = true
            }
        } catch {
            // 同上
            isAuthenticated = true
        }
    }

    /// APIClient 刷新失败后的强制登出入口
    private func handleSessionExpired() {
        clearLocalSession()
    }

    private func persist(accessToken: String, refreshToken: String) async {
        KeychainHelper.save(accessToken, account: AppConstants.keychainAccountAccessToken)
        KeychainHelper.save(refreshToken, account: AppConstants.keychainAccountRefreshToken)
        await APIClient.shared.setTokens(accessToken: accessToken, refreshToken: refreshToken)
    }

    private func clearLocalSession() {
        KeychainHelper.delete(account: AppConstants.keychainAccountAccessToken)
        KeychainHelper.delete(account: AppConstants.keychainAccountRefreshToken)
        Task {
            await APIClient.shared.clearTokens()
        }
        currentUser = nil
        isAuthenticated = false
    }
}
