import Foundation

// MARK: - 情绪聚合模型（逐字段对齐 app/api/v1/research.py 的
// SentimentDataAggregateItem —— 注意后端实际返回 instrument_code，
// web ts 类型里的 symbol 是前端命名，以后端为准）

/// GET /research/sentiment-data/aggregate 单项（按标的聚合的新闻情绪）
struct SentimentAggregateItem: Codable, Sendable, Identifiable {
    var id: String { instrumentCode }
    /// 标的代码（后端字段名 instrument_code）
    let instrumentCode: String
    /// 贡献记录数
    let count: Int
    /// 平均情绪分 [-1, 1]
    let avgScore: Double
    /// positive / negative / neutral（复用 NewsModels 的 SentimentLabel）
    let label: SentimentLabel
    /// 看多 / 看空 / 中性 条数
    let bull: Int
    let bear: Int
    let neutral: Int
    /// 近 14 日每日平均分（oldest → newest，缺日补 0）
    let sparkline: [Double]
    let name: String?
    let nameZh: String?
    let latestTitle: String?
    /// ISO8601
    let latestPublishedAt: String?

    var displayName: String {
        if let nameZh, !nameZh.isEmpty { return nameZh }
        if let name, !name.isEmpty { return name }
        return instrumentCode
    }
}

/// GET /research/sentiment-data/aggregate 响应信封
struct SentimentAggregateResponse: Decodable, Sendable {
    let items: [SentimentAggregateItem]
}
