import Foundation

/// JSON 编解码统一入口。
///
/// 后端为 FastAPI/Pydantic，字段一律 snake_case，因此：
/// - 解码：``.convertFromSnakeCase``（模型层全部用 camelCase 属性）
/// - 编码：``.convertToSnakeCase``（请求体模型同样写 camelCase）
///
/// 时间字段策略：DTO 中一律保留 ``String``（后端混用 ``YYYY-MM-DD`` 与
/// ISO8601 带/不带毫秒的 datetime），由 ``DateFormatting`` 统一解析，
/// 避免全局 dateDecodingStrategy 在混合格式上翻车。
enum JSONCoding {
    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()
}
