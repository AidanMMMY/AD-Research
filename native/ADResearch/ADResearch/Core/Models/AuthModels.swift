import Foundation

// MARK: - 认证模型（逐字段对齐 web/src/api/auth.ts）

/// POST /auth/login 请求体
struct LoginRequest: Encodable, Sendable {
    let username: String
    let password: String
}

/// POST /auth/refresh 请求体
struct RefreshRequest: Encodable, Sendable {
    let refreshToken: String
}

/// 用户资料（``UserProfile``）。
/// ts 契约 role 为 'admin' | 'user'，这里保留 String——后端将来加角色不至于解码崩。
struct UserProfile: Codable, Sendable, Equatable {
    let id: Int
    let username: String
    /// 'admin' | 'user'
    let role: String
}

/// POST /auth/login 响应
struct LoginResponse: Decodable, Sendable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let user: UserProfile
}

/// POST /auth/refresh 响应
struct RefreshResponse: Decodable, Sendable {
    let accessToken: String
    let refreshToken: String
}
