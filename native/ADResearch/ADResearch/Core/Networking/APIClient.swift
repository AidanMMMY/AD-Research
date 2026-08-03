import Foundation

/// 统一网络层（对齐 web 端 axios 实例 ``web/src/api/client.ts`` 的行为）：
///
/// - ``actor`` 保证并发安全；所有请求 async/await
/// - 请求自动携带 ``Authorization: Bearer <access_token>``
/// - 401 → 单飞（single-flight）``/auth/refresh`` → 原请求重放一次
///   （对齐 web 的 isRefreshing + refreshQueue：并发请求共享同一次刷新）
/// - 刷新失败 → 清空令牌 + 回调 AuthStore 强制登出（对齐 web 的清 localStorage + 跳 /login）
/// - DEBUG 下打印请求日志（脱敏 Authorization 头）
actor APIClient {
    static let shared = APIClient()

    private let session: URLSession

    private var accessToken: String?
    private var refreshToken: String?

    /// 单飞刷新：并发 401 共享同一个刷新 Task
    private var inFlightRefresh: Task<RefreshResponse, Error>?

    /// 会话彻底失效回调（由 AuthStore 在启动时注册）
    private var sessionExpiredHandler: (@Sendable () -> Void)?

    /// 刷新成功后回调新令牌对（后端会轮换 refresh_token，
    /// 对齐 web 注释：不持久化新 refresh_token 会话即死）
    private var tokensUpdatedHandler: (@Sendable (_ accessToken: String, _ refreshToken: String) -> Void)?

    init(session: URLSession = .shared) {
        self.session = session
    }

    // MARK: - 令牌管理（由 AuthStore 调用）

    func setTokens(accessToken: String, refreshToken: String) {
        self.accessToken = accessToken
        self.refreshToken = refreshToken
    }

    func clearTokens() {
        accessToken = nil
        refreshToken = nil
    }

    func setSessionExpiredHandler(_ handler: (@Sendable () -> Void)?) {
        sessionExpiredHandler = handler
    }

    func setTokensUpdatedHandler(_ handler: (@Sendable (_ accessToken: String, _ refreshToken: String) -> Void)?) {
        tokensUpdatedHandler = handler
    }

    // MARK: - 发送请求

    /// 发送并解码响应体
    func send<T: Decodable>(_ endpoint: Endpoint, as type: T.Type = T.self) async throws -> T {
        let data = try await perform(endpoint)
        do {
            return try JSONCoding.decoder.decode(T.self, from: data)
        } catch {
            log("解码失败 \(endpoint.path): \(error)")
            throw APIError.decodingFailed(error.localizedDescription)
        }
    }

    /// 发送但忽略响应体（如 logout）
    func send(_ endpoint: Endpoint) async throws {
        _ = try await perform(endpoint)
    }

    // MARK: - 核心流程：请求 → 401 → 单飞刷新 → 重放一次

    private func perform(_ endpoint: Endpoint) async throws -> Data {
        let request = try buildRequest(endpoint)
        var (data, response) = try await execute(request, path: endpoint.path)

        if response.statusCode == 401, endpoint.requiresAuth, !endpoint.isRefreshCall {
            guard refreshToken != nil else {
                notifySessionExpired()
                throw APIError.unauthorized
            }
            log("401，尝试单飞刷新：\(endpoint.path)")
            do {
                let tokens = try await refreshTokensSingleFlight()
                accessToken = tokens.accessToken
                refreshToken = tokens.refreshToken
                notifyTokensUpdated(access: tokens.accessToken, refresh: tokens.refreshToken)
            } catch {
                // 刷新失败 = 会话死亡（对齐 web：清令牌 + 强制登出）
                clearTokens()
                notifySessionExpired()
                throw APIError.unauthorized
            }
            // 原请求重放一次（对齐 web 的 originalRequest._retry = true）
            let retryRequest = try buildRequest(endpoint)
            (data, response) = try await execute(retryRequest, path: endpoint.path)
            if response.statusCode == 401 {
                clearTokens()
                notifySessionExpired()
                throw APIError.unauthorized
            }
        }

        switch response.statusCode {
        case 200...299:
            return data
        case 401:
            throw APIError.unauthorized
        case 404:
            throw APIError.notFound(Self.serverMessage(from: data))
        default:
            throw APIError.httpError(status: response.statusCode, message: Self.serverMessage(from: data))
        }
    }

    /// 单飞刷新：已有刷新在进行时直接 await 同一个 Task
    private func refreshTokensSingleFlight() async throws -> RefreshResponse {
        if let task = inFlightRefresh {
            return try await task.value
        }
        guard let token = refreshToken else {
            throw APIError.unauthorized
        }
        let task = Task<RefreshResponse, Error> {
            let endpoint = try Endpoint.authRefresh(RefreshRequest(refreshToken: token))
            let request = try self.buildRequest(endpoint)
            let (data, response) = try await self.execute(request, path: endpoint.path)
            guard (200...299).contains(response.statusCode) else {
                throw APIError.httpError(status: response.statusCode, message: Self.serverMessage(from: data))
            }
            do {
                return try JSONCoding.decoder.decode(RefreshResponse.self, from: data)
            } catch {
                throw APIError.decodingFailed(error.localizedDescription)
            }
        }
        inFlightRefresh = task
        defer { inFlightRefresh = nil }
        return try await task.value
    }

    // MARK: - 请求构造与执行

    private func buildRequest(_ endpoint: Endpoint) throws -> URLRequest {
        let base = AppConstants.apiBaseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard var components = URLComponents(string: base + endpoint.path) else {
            throw APIError.invalidURL
        }
        if !endpoint.queryItems.isEmpty {
            components.queryItems = endpoint.queryItems
        }
        guard let url = components.url else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url, timeoutInterval: AppConstants.requestTimeout)
        request.httpMethod = endpoint.method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if endpoint.requiresAuth, let accessToken {
            request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = endpoint.body
        return request
    }

    private func execute(_ request: URLRequest, path: String) async throws -> (Data, HTTPURLResponse) {
        let started = Date()
        do {
            let (data, response) = try await dataForRequest(request)
            guard let http = response as? HTTPURLResponse else {
                throw APIError.network("响应格式异常")
            }
            log("\(request.httpMethod ?? "?") \(path) → \(http.statusCode)（\(Int(Date().timeIntervalSince(started) * 1000))ms）")
            return (data, http)
        } catch let error as APIError {
            throw error
        } catch let urlError as URLError {
            log("\(request.httpMethod ?? "?") \(path) → 网络错误 \(urlError.code.rawValue)")
            throw APIError.network(Self.networkMessage(for: urlError))
        } catch {
            throw APIError.network(error.localizedDescription)
        }
    }

    /// 抽出来以便子类/测试覆写（当前直接用 session）
    private func dataForRequest(_ request: URLRequest) async throws -> (Data, URLResponse) {
        try await session.data(for: request)
    }

    private func notifySessionExpired() {
        let handler = sessionExpiredHandler
        // 回调离开 actor 隔离域执行，避免重入死锁
        Task.detached {
            handler?()
        }
    }

    private func notifyTokensUpdated(access: String, refresh: String) {
        let handler = tokensUpdatedHandler
        Task.detached {
            handler?(access, refresh)
        }
    }

    // MARK: - 错误消息提取（FastAPI 错误信封）

    /// FastAPI 错误体两种形态：``{"detail": "..."}`` 或 ``{"detail": [{"msg": "..."}]}``
    private static func serverMessage(from data: Data) -> String? {
        struct DetailString: Decodable { let detail: String }
        struct DetailItem: Decodable { let msg: String }
        struct DetailList: Decodable { let detail: [DetailItem] }
        if let envelope = try? JSONDecoder().decode(DetailString.self, from: data) {
            return envelope.detail
        }
        if let envelope = try? JSONDecoder().decode(DetailList.self, from: data) {
            return envelope.detail.map(\.msg).joined(separator: "；")
        }
        return nil
    }

    private static func networkMessage(for error: URLError) -> String {
        switch error.code {
        case .notConnectedToInternet, .dataNotAllowed:
            return "网络连接不可用，请检查网络设置"
        case .timedOut:
            return "请求超时，请稍后重试"
        case .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed:
            return "无法连接服务器，请稍后重试"
        case .cancelled:
            return "请求已取消"
        default:
            return "网络请求失败（\(error.code.rawValue)）"
        }
    }

    // MARK: - 调试日志（仅 DEBUG，脱敏令牌）

    private nonisolated func log(_ message: String) {
        #if DEBUG
        print("[APIClient] \(message)")
        #endif
    }
}
