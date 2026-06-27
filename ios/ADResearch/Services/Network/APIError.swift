import Foundation

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case unauthorized
    case serverError(Int)
    case networkError(Error)
    case decodingError(Error)
    case unknown

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "无效的请求地址"
        case .invalidResponse:
            return "服务器响应异常"
        case .unauthorized:
            return "登录已过期，请重新登录"
        case .serverError(let code):
            return "服务器错误 (\(code))"
        case .networkError(let error):
            return error.localizedDescription
        case .decodingError:
            return "数据解析失败"
        case .unknown:
            return "未知错误"
        }
    }
}
