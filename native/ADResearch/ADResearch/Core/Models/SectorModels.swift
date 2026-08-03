import Foundation

// MARK: - 板块轮动模型（逐字段对齐 web/src/types/sector_rotation.ts +
// app/schemas/sector_rotation.py；SW 模式的官方指数字段暂不建模，移动端列表用不到）

/// GET /sector-rotation 单项（板块表现）
struct SectorPerformance: Codable, Sendable, Identifiable {
    var id: String { sector }
    let sector: String
    let count: Int
    let stockCount: Int
    let etfCount: Int
    let return1w: Double
    let return1m: Double
    let return3m: Double
    let return6m: Double
    let return1y: Double
    let sharpe1y: Double
    let volatility20d: Double
    let rsi14: Double
    let amountTotal: Double
    let relativeStrength1w: Double
    let relativeStrength1m: Double
    let relativeStrength3m: Double
    let momentumRank: Int
}

/// GET /sector-rotation 市场均值
struct SectorMarketAverage: Codable, Sendable {
    let return1w: Double
    let return1m: Double
    let return3m: Double
    let return6m: Double
    let return1y: Double
    let sharpe1y: Double
}

/// 轮动信号（ts type: 'up' | 'down'，保留 String 防后端扩展）
struct RotationSignal: Codable, Sendable, Identifiable {
    var id: String { "\(sector)|\(type)|\(currentRank)" }
    let sector: String
    let type: String
    let message: String
    let currentRank: Int
    let previousRank: Int
    let rankChange: Int
}

/// 分析范围（ts 里 market 是字面量 'A股'，收敛为 String）
struct SectorScope: Codable, Sendable {
    let market: String
    let instrumentTypes: [String]
    let classification: String
}

/// GET /sector-rotation 响应
struct SectorRotationResponse: Decodable, Sendable {
    /// YYYY-MM-DD，可能为 nil（无数据）
    let tradeDate: String?
    let scope: SectorScope
    let sectors: [SectorPerformance]
    let marketAvg: SectorMarketAverage?
    let rotationSignals: [RotationSignal]
}
