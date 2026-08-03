import Foundation

// MARK: - 评分 / 自选状态 / 平台统计模型（2026-08-04 标的详情升级 + Dashboard 整改新增）
//
// 契约核对记录：
// - ``InstrumentScore`` ← ``app/schemas/scoring.py`` ETFScoreResponse（L53-81）：
//   除 etf_code 外全部 Optional；rank_overall_original 仅榜单端点填充，单标的端点不返回，
//   故不建模（Decodable 对多余/缺失键均容错）。
// - ``FavoriteStatusResponse`` ← ``app/api/v1/favorites.py`` check_favorite：
//   ``FavoriteStatusResponse(etf_code=..., is_favorite=...)``。
//   （FavoriteToggleResponse 已有，见 PortfolioModels.swift）
// - ``StatsOverview`` ← ``app/api/v1/stats.py`` _collect_overview：裸 dict、无 Pydantic
//   schema，逐字段核对返回值：etf_count / category_count / market_count /
//   indicator_count / score_count / template_count / latest_indicator_date /
//   latest_score_date（后两者为 date.isoformat() 或 null）。
//
// 解码走 JSONCoding.decoder（.convertFromSnakeCase），Swift 属性均为 camelCase。

/// GET /scores/{code} — 单标的最新评分（总分 + 五分项 + 排名 + 区间收益）。
/// 404 = 该标的无评分记录，消费方按「整卡隐藏」处理（参考 isNotFound 模式）。
struct InstrumentScore: Decodable, Sendable {
    let etfCode: String
    let etfName: String?
    let nameZh: String?
    let market: String?
    let category: String?
    let instrumentType: String?
    /// YYYY-MM-DD（评分快照交易日）
    let tradeDate: String?
    /// 综合分（0-100）
    let compositeScore: Double?
    /// 收益分项（0-100）
    let scoreReturn: Double?
    /// 风险分项（0-100）
    let scoreRisk: Double?
    /// 夏普分项（0-100）
    let scoreSharpe: Double?
    /// 流动性分项（0-100）
    let scoreLiquidity: Double?
    /// 趋势分项（0-100）
    let scoreTrend: Double?
    /// 全市场排名
    let rankOverall: Int?
    /// 分类内排名
    let rankCategory: Int?
    /// 近 1 月收益（%）
    let return1m: Double?
    /// 近 3 月收益（%）
    let return3m: Double?
    /// 近 1 年收益（%）
    let return1y: Double?

    /// 展示名（中文优先）
    var displayName: String? {
        if let nameZh, !nameZh.isEmpty { return nameZh }
        return etfName
    }
}

/// GET /favorites/{code}/status — 单标的自选状态
struct FavoriteStatusResponse: Decodable, Sendable {
    let etfCode: String
    let isFavorite: Bool
}

/// GET /stats/overview — 平台 KPI 总览（Dashboard 第三栏真数据卡）
struct StatsOverview: Decodable, Sendable {
    /// 标的总数
    let etfCount: Int
    /// 分类数
    let categoryCount: Int
    /// 市场数
    let marketCount: Int
    /// 指标行数
    let indicatorCount: Int
    /// 评分行数
    let scoreCount: Int
    /// 评分模板数
    let templateCount: Int
    /// 最新指标交易日（YYYY-MM-DD，可能为 null）
    let latestIndicatorDate: String?
    /// 最新评分交易日（YYYY-MM-DD，可能为 null）
    let latestScoreDate: String?
}
