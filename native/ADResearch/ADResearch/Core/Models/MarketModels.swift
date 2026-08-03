import Foundation

// MARK: - 加密行情模型（逐字段对齐 web/src/types/crypto.ts + web/src/api/crypto.ts）

/// GET /crypto 列表项（已 enrich 实时价）。
/// 注意：契约无市值字段（web CryptoList 同样没有市值列），
/// 列表展示用 24h 成交量代替。
struct CryptoInfo: Codable, Sendable, Identifiable {
    var id: String { code }
    let code: String
    let name: String
    let nameZh: String?
    let exchange: String?
    let market: String?
    let category: String?
    let currency: String?
    let instrumentType: String?
    let status: String?
    /// 最新价（USDT）
    let price: Double?
    /// 24h 涨跌幅（%），canonical 字段；deprecated 的 change_24h 不建模
    let changePct: Double?
    /// 24h 成交量（base asset）
    let volume24h: Double?
    /// 实时价抓取时间（UTC ISO8601）
    let lastUpdated: String?

    var displayName: String {
        if let nameZh, !nameZh.isEmpty { return nameZh }
        return name
    }
}

/// GET /crypto 响应（分页信封）
struct CryptoListResponse: Decodable, Sendable {
    let items: [CryptoInfo]
    let total: Int
    let page: Int
    let pageSize: Int

    var totalPages: Int {
        guard pageSize > 0 else { return 1 }
        return max(Int(ceil(Double(total) / Double(pageSize))), 1)
    }
}
