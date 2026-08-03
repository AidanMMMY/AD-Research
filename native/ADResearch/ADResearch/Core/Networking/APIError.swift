import Foundation

/// API 错误类型（对齐 web axios 拦截器的语义分层）。
///
/// - 401 且无法刷新会话：``.unauthorized``（AuthStore 收到后强制登出）
/// - 404：``.notFound``——后端部分端点（如 ``/digest/latest/summary``）用 404
///   表达「空态」而非错误，调用方用 ``isNotFound`` 判定
/// - 其余非 2xx：``.httpError``，携带后端 ``detail`` 字段的中文/英文消息
enum APIError: Error, Equatable {
    /// URL 组装失败（理论上不该发生，防御性分支）
    case invalidURL
    /// 网络层错误（断网、超时、DNS 等）
    case network(String)
    /// 401——未认证或刷新失败后的最终态
    case unauthorized
    /// 404——资源不存在（部分端点等价于「空态」）
    case notFound(String?)
    /// 其他非 2xx 响应
    case httpError(status: Int, message: String?)
    /// 响应体解码失败
    case decodingFailed(String)
    /// 请求体编码失败
    case encodingFailed(String)

    /// 是否为 404 空态（web 端 ``isDigestNotFound`` 的对应物）
    var isNotFound: Bool {
        if case .notFound = self { return true }
        return false
    }

    /// 是否为「离线/超时」类错误（区别于服务端业务错误）
    var isNetworkFailure: Bool {
        if case .network = self { return true }
        return false
    }

    /// 面向用户的中文描述
    var userMessage: String {
        switch self {
        case .invalidURL:
            return "请求地址无效"
        case .network(let message):
            return message
        case .unauthorized:
            return "登录状态已过期，请重新登录"
        case .notFound(let message):
            return message ?? "内容不存在"
        case .httpError(let status, let message):
            if let message, !message.isEmpty { return message }
            return "服务器错误（\(status)）"
        case .decodingFailed:
            return "数据解析失败，请稍后重试"
        case .encodingFailed:
            return "请求构造失败"
        }
    }
}
