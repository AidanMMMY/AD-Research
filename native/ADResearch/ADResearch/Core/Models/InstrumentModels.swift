import Foundation

// MARK: - 标的模型（逐字段对齐 web/src/types/instrument.ts + web/src/api/instrument.ts）

/// GET /etfs 列表项 / GET /etfs/{code} 详情（同一 schema）
struct InstrumentInfo: Codable, Sendable, Identifiable {
    var id: String { code }
    let code: String
    let name: String
    let nameZh: String?
    let market: String
    let exchange: String?
    let category: String?
    let subCategory: String?
    let manager: String?
    let fundManager: String?
    let fundSize: Double?
    let underlyingIndex: String?
    let expenseRatio: Double?
    let currency: String?
    let isQdii: Bool?
    /// YYYY-MM-DD
    let inceptionDate: String?
    let status: String?
    let instrumentType: String?
    let sector: String?
    let industry: String?
    let marketCap: Double?
    let country: String?
    /// A 股上市地（上海/深圳/北京），非 A 股为 nil
    let listingMarket: String?
    /// A 股板块（主板/创业板/科创板/北交所）
    let board: String?

    /// 展示名：中文名优先
    var displayName: String {
        if let nameZh, !nameZh.isEmpty { return nameZh }
        return name
    }

    /// 市场中文标签（DB 值：A股 / US / HK / CRYPTO）
    var marketLabel: String {
        switch market {
        case "US": return "美股"
        case "HK": return "港股"
        case "CRYPTO": return "加密"
        default: return market
        }
    }
}

/// GET /etfs 响应（分页信封）
struct InstrumentListResponse: Decodable, Sendable {
    let items: [InstrumentInfo]
    let total: Int
    let page: Int
    let pageSize: Int

    var totalPages: Int {
        guard pageSize > 0 else { return 1 }
        return max(Int(ceil(Double(total) / Double(pageSize))), 1)
    }
}

/// GET /etfs/{code}/sparkline?days= 响应
/// （后端 app/api/v1/etfs.py：oldest → newest 收盘序列，days 上限 365）
struct InstrumentSparklineResponse: Decodable, Sendable {
    let code: String
    let days: Int
    let points: [Double]
    /// YYYY-MM-DD，与 points 等长
    let dates: [String]
}

/// GET /etfs/markets/list 响应
struct InstrumentMarketsResponse: Decodable, Sendable {
    let markets: [String]
}
