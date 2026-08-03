import Foundation

// MARK: - 组合/自选模型（逐字段对齐 web/src/types/favorite.ts + pool.ts，
// 行情快照字段以后端 app/schemas/market_data.py 为准——web ts 的
// MarketSnapshot（code/name/change_percent）是过期接口，实际线报文为
// etf_code/etf_name/close/change_pct/volume/amount）

/// 自选标的（GET /favorites 列表项）
struct FavoriteItem: Decodable, Sendable, Identifiable, Equatable {
    let etfCode: String
    let etfName: String?
    let category: String?
    let market: String?
    let createdAt: String?

    var id: String { etfCode }
}

/// GET /favorites 响应
struct FavoriteListResponse: Decodable, Sendable {
    let items: [FavoriteItem]
    let count: Int
}

/// POST /favorites/{code}/toggle、DELETE /favorites/{code} 响应
struct FavoriteToggleResponse: Decodable, Sendable {
    let etfCode: String
    let isFavorite: Bool
    let message: String
}

/// GET /market-data/snapshot 单项（后端 SnapshotItem）。
/// ``changePct`` 单位是百分数（1.23 = 涨 1.23%），直接喂给 ``ChangeText``。
struct MarketSnapshotItem: Decodable, Sendable, Equatable {
    let etfCode: String
    let etfName: String?
    let close: Double?
    let changePct: Double?
    let volume: Int?
    let amount: Double?
}

/// GET /market-data/snapshot 响应
struct MarketSnapshotResponse: Decodable, Sendable {
    let items: [MarketSnapshotItem]
    let count: Int
}

/// 标的池成员（后端 PoolMemberResponse；web ts 的 ``note`` 实为 ``notes``）
struct PoolMember: Decodable, Sendable, Equatable {
    let etfCode: String
    let etfName: String?
    let nameZh: String?
    let addedAt: String?
    let notes: String?
}

/// 标的池（GET /pools 列表项，后端 PoolResponse）。
/// ``userId`` 为 nil = 系统预置的全局共享池（仅管理员可删改）。
struct InstrumentPool: Decodable, Sendable, Identifiable, Equatable {
    let id: Int
    let name: String
    let description: String?
    let userId: Int?
    let members: [PoolMember]
    let createdAt: String?
    let updatedAt: String?

    /// 是否系统预置池
    var isPreset: Bool { userId == nil }
}
