import Foundation

// MARK: - 宏观模型（逐字段对齐 web/src/types/macro.ts + app/api/v1/macro.py）

/// 区域：cn / eu / us / global
enum MacroRegion: String, Codable, Sendable {
    case cn
    case eu
    case us
    case global
}

/// GET /macro/latest 单项（最新快照）
struct MacroLatestItem: Codable, Sendable, Identifiable {
    var id: String { "\(code)|\(region)" }
    let code: String
    let region: String
    let nameZh: String
    let nameEn: String?
    let unit: String?
    let source: String
    /// ISO 日期（YYYY-MM-DD）
    let period: String
    let value: Double
    let prevValue: Double?
    let changePct: Double?
    let fetchedAt: String?
}

/// GET /macro/latest 响应
struct MacroLatestResponse: Decodable, Sendable {
    let items: [MacroLatestItem]
}

/// GET /macro/indices/global 单项（实时快照；后端契约见
/// ``app/api/v1/macro.py``：{code, name_zh, name_en, unit, value,
/// prev_close, change, change_pct, as_of, source, region, asset_class}，
/// 内部 code 与 /macro/latest 一致，如 global_sp500）
struct GlobalIndexRealtimeItem: Codable, Sendable, Identifiable {
    var id: String { code }
    let code: String
    let nameZh: String?
    let nameEn: String?
    let unit: String?
    let value: Double?
    let prevClose: Double?
    let change: Double?
    let changePct: Double?
    let asOf: String?
    let source: String?
    let region: String?
    let assetClass: String?
}

/// GET /macro/indices/global 响应信封
struct GlobalIndicesRealtimeResponse: Decodable, Sendable {
    let items: [GlobalIndexRealtimeItem]
    let region: String?
    let asOf: String?
    let count: Int?
    /// as_of 超过 24h 的条目数（后端单一事实来源）
    let staleCount: Int?
}

/// GET /macro/indicators/{code} 单点（period=YYYY-MM-DD）
struct MacroSeriesPoint: Codable, Sendable, Identifiable {
    var id: String { period }
    let period: String
    let value: Double
}

/// GET /macro/indicators/{code} 时间序列（对齐 MacroIndicatorSeries）
struct MacroIndicatorSeries: Decodable, Sendable {
    let code: String
    let region: String
    let nameZh: String
    let nameEn: String?
    let unit: String
    let source: String
    let points: [MacroSeriesPoint]
}
