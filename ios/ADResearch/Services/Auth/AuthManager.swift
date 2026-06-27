import Foundation

/// Central authentication manager — login, logout, token refresh.
@MainActor
final class AuthManager: ObservableObject {
    static let shared = AuthManager()

    @Published var isAuthenticated = false
    @Published var currentUser: UserDTO?

    private let keychain = KeychainStore.shared
    private let authService = AuthService(baseURL: APIClient.shared.baseURL)

    private var refreshTask: Task<String?, Never>?

    // MARK: - Public

    var accessToken: String? {
        get async { await keychain.accessToken }
    }

    var refreshToken: String? {
        get async { await keychain.refreshToken }
    }

    func restoreSession() async {
        guard let refresh = await keychain.refreshToken, !refresh.isEmpty else { return }
        do {
            let response = try await authService.refresh(refreshToken: refresh)
            await keychain.accessToken = response.accessToken
            let user: UserDTO = try await APIClient.shared.get("/auth/me")
            currentUser = user
            isAuthenticated = true
        } catch {
            await keychain.clear()
            isAuthenticated = false
        }
    }

    func login(username: String, password: String) async throws {
        let response = try await authService.login(username: username, password: password)
        await keychain.accessToken = response.accessToken
        await keychain.refreshToken = response.refreshToken
        currentUser = response.user
        isAuthenticated = true
    }

    func refreshTokenIfNeeded() async throws -> String? {
        // Deduplicate concurrent refresh attempts
        if let existing = refreshTask {
            return await existing.value
        }

        refreshTask = Task { [weak self] in
            guard let self else { return nil }
            guard let refresh = await keychain.refreshToken else { return nil }
            do {
                let response = try await authService.refresh(refreshToken: refresh)
                await keychain.accessToken = response.accessToken
                return response.accessToken
            } catch {
                await keychain.clear()
                await MainActor.run {
                    self.isAuthenticated = false
                    self.currentUser = nil
                }
                return nil
            }
        }

        let token = await refreshTask!.value
        refreshTask = nil
        return token
    }

    func logout() async {
        _ = try? await authService.logout(accessToken: await keychain.accessToken ?? "")
        await keychain.clear()
        currentUser = nil
        isAuthenticated = false
    }

    func registerDevice(name: String, platform: String, pushToken: String?) async {
        _ = try? await authService.registerDevice(
            name: name, platform: platform, pushToken: pushToken
        )
    }
}
