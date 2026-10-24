import Foundation

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case unauthorized
    case serverError(Int)
    case serverMessage(String)
    case networkError(Error)
    case decodingError(Error)
    case unknown

    static func fromResponse(statusCode: Int, data: Data) -> APIError {
        struct DetailResponse: Decodable { let detail: String }
        if let response = try? JSONDecoder().decode(DetailResponse.self, from: data) {
            let detail = response.detail.trimmingCharacters(in: .whitespacesAndNewlines)
            if !detail.isEmpty { return .serverMessage(detail) }
        }
        return .serverError(statusCode)
    }

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
        case .serverMessage(let message):
            return message
        case .networkError(let error):
            return error.localizedDescription
        case .decodingError:
            return "数据解析失败"
        case .unknown:
            return "未知错误"
        }
    }
}
