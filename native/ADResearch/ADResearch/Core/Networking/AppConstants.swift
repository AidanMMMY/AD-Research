import Foundation

/// 全局常量。
enum AppConstants {
    /// 生产后端 base URL（对齐 web 端 ``VITE_API_BASE_URL || '/api/v1'``）。
    /// 调试时可在 Settings 里切换，或通过环境变量 ``AD_API_BASE_URL`` 覆盖。
    static let defaultAPIBaseURL = URL(string: "https://alloyresearch.net/api/v1")!

    /// 当前生效的 base URL：环境变量 > UserDefaults 覆盖 > 生产默认。
    static var apiBaseURL: URL {
        if let env = ProcessInfo.processInfo.environment["AD_API_BASE_URL"],
           let url = URL(string: env), !env.isEmpty {
            return url
        }
        if let override = UserDefaults.standard.string(forKey: "api_base_url_override"),
           let url = URL(string: override), !override.isEmpty {
            return url
        }
        return defaultAPIBaseURL
    }

    /// 请求超时（对齐 web axios timeout = 30s）
    static let requestTimeout: TimeInterval = 30

    /// Keychain service 标识
    static let keychainService = "net.alloyresearch.ADResearch"
    /// Keychain account：访问令牌
    static let keychainAccountAccessToken = "access_token"
    /// Keychain account：刷新令牌
    static let keychainAccountRefreshToken = "refresh_token"
}
