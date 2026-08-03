import Foundation

// MARK: - 资金流模型（逐字段对齐 app/schemas/fund_flow.py；
// decoder 全局 convertFromSnakeCase，字段直接驼峰）

/// 大盘整体资金流（GET /fund-flow/market，单日快照；
/// 后端无数据时返回全 null 占位对象，调用方按空态处理）。
struct MarketFundFlow: Decodable, Sendable, Equatable {
    let tradeDate: String
    let shMainNetInflow: Double?
    let szMainNetInflow: Double?
    let shMainNetPct: Double?
    let szMainNetPct: Double?
    /// 沪深整体主力净流入（market='ALL' 行）
    let totalMainNetInflow: Double?
    /// 沪深整体主力净流入占比（%）
    let totalMainNetPct: Double?
}

/// 板块资金流记录（行业/概念/地域）。
struct SectorFundFlow: Decodable, Sendable, Identifiable, Equatable {
    let id: Int
    let sectorName: String
    /// 板块类型：行业 / 概念 / 地域
    let sectorType: String
    let tradeDate: String
    let mainNetInflow: Double?
    /// 主力净流入占比（%）
    let mainNetPct: Double?
    let superLargeNet: Double?
    let largeNet: Double?
    let leadingStock: String?
}

struct SectorFundFlowListResponse: Decodable, Sendable {
    let items: [SectorFundFlow]
    let total: Int
    let page: Int
    let pageSize: Int
}

/// ETF 资金流记录（份额变动推算净流入）。
struct EtfFundFlow: Decodable, Sendable, Identifiable, Equatable {
    let id: Int
    let tsCode: String
    let tradeDate: String
    let price: Double?
    let netValue: Double?
    /// 溢价率（%）
    let premiumRate: Double?
    let sharesOutstanding: Double?
    let sharesChange: Double?
    let turnover: Double?
    /// 推算净流入
    let inferredNetInflow: Double?
}

struct EtfFundFlowListResponse: Decodable, Sendable {
    let items: [EtfFundFlow]
    let total: Int
    let page: Int
    let pageSize: Int
}

/// 综合资金信号（主力/两融/龙虎榜/股东户数/AH溢价/大宗 六维合成）。
struct FlowSignal: Decodable, Sendable, Identifiable, Equatable {
    let id: Int
    let tsCode: String
    let tradeDate: String
    let mainNetInflow: Double?
    let marginNetChange: Double?
    let lhbNetBuy: Double?
    let shareholderCountChange: Double?
    let ahPremium: Double?
    let blockTradeNet: Double?
    /// 六维综合分（越高资金越看多）
    let compositeScore: Double?
}

struct FlowSignalListResponse: Decodable, Sendable {
    let items: [FlowSignal]
    let total: Int
    let page: Int
    let pageSize: Int
}

// MARK: - 展示辅助

enum FundFlowFormat {
    /// 金额格式化（镜像 web FundFlow `formatMoney`）：≥1 亿→「x.xx 亿」，
    /// ≥1 万→「x.xx 万」；负号保留、正数不加 +；null → —。
    static func money(_ value: Double?, digits: Int = 2) -> String {
        guard let value, !value.isNaN else { return "—" }
        let absV = abs(value)
        let sign = value < 0 ? "-" : ""
        if absV >= 1e8 {
            return "\(sign)\(String(format: "%.\(digits)f", absV / 1e8)) 亿"
        }
        if absV >= 1e4 {
            return "\(sign)\(String(format: "%.\(digits)f", absV / 1e4)) 万"
        }
        return "\(sign)\(String(format: "%.\(digits)f", absV))"
    }

    /// 百分数（镜像 web `formatPct`）：正数补 +，负数自带 −。
    static func pct(_ value: Double?, digits: Int = 2) -> String {
        guard let value, !value.isNaN else { return "—" }
        let sign = value > 0 ? "+" : ""
        return "\(sign)\(String(format: "%.\(digits)f", value))%"
    }
}
