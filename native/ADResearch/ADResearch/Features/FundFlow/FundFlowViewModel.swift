import Foundation

/// 资金流 ViewModel。
///
/// 契约（app/api/v1/fund_flow.py，全部 A 股语境）：
/// - GET /fund-flow/market → MarketFundFlow 单日快照（无数据时后端返全 null 占位）
/// - GET /fund-flow/sector → SectorFundFlowListResponse（行业/概念/地域混合）
/// - GET /fund-flow/etf → EtfFundFlowListResponse
/// - GET /fund-flow/signals → FlowSignalListResponse（六维综合分）
///
/// 结构对齐 web FundFlow 页：顶部大盘快照卡 + 分段（板块/ETF/信号）列表。
@MainActor
@Observable
final class FundFlowViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    enum Segment: String, CaseIterable, Identifiable {
        case sector
        case etf
        case signal

        var id: String { rawValue }

        var label: String {
            switch self {
            case .sector: return "板块"
            case .etf: return "ETF"
            case .signal: return "资金信号"
            }
        }
    }

    var segment: Segment = .sector {
        didSet {
            if segment != oldValue {
                Task { await reloadSegment() }
            }
        }
    }

    /// 板块类型过滤（行业 / 概念 / 地域 / 全部），客户端过滤
    enum SectorTypeFilter: String, CaseIterable, Identifiable {
        case all
        case industry = "行业"
        case concept = "概念"
        case region = "地域"

        var id: String { rawValue }
        var label: String { self == .all ? "全部" : rawValue }
    }

    var sectorType: SectorTypeFilter = .all

    private(set) var market: MarketFundFlow?
    private(set) var sectors: [SectorFundFlow] = []
    private(set) var etfs: [EtfFundFlow] = []
    private(set) var signals: [FlowSignal] = []
    private(set) var tradeDate: String?
    private(set) var state: LoadState = .idle

    private var hasLoadedOnce = false

    /// 当前分段按过滤条件处理后的列表（板块段用）
    var filteredSectors: [SectorFundFlow] {
        let base = sectorType == .all ? sectors : sectors.filter { $0.sectorType == sectorType.rawValue }
        return base.sorted { abs($0.mainNetInflow ?? 0) > abs($1.mainNetInflow ?? 0) }
    }

    var sortedEtfs: [EtfFundFlow] {
        etfs.sorted { abs($0.inferredNetInflow ?? 0) > abs($1.inferredNetInflow ?? 0) }
    }

    var sortedSignals: [FlowSignal] {
        signals.sorted { ($0.compositeScore ?? 0) > ($1.compositeScore ?? 0) }
    }

    func loadIfNeeded() async {
        guard !hasLoadedOnce else { return }
        hasLoadedOnce = true
        await reload()
    }

    /// 全量：大盘快照 + 三个分段并行拉取（分段多但每路 limit 50，量级小）
    func reload() async {
        if state == .idle { state = .loading }
        async let marketTask: () = loadMarket()
        async let sectorTask: () = loadSectors()
        async let etfTask: () = loadEtfs()
        async let signalTask: () = loadSignals()
        _ = await (marketTask, sectorTask, etfTask, signalTask)
        if market != nil || !sectors.isEmpty || !etfs.isEmpty || !signals.isEmpty {
            state = .loaded
        } else if state == .loading {
            state = .failed("加载失败，请稍后重试")
        }
    }

    /// 分段切换时的懒加载：只拉当前分段（若已有数据则跳过）
    func reloadSegment() async {
        switch segment {
        case .sector where sectors.isEmpty: await loadSectors()
        case .etf where etfs.isEmpty: await loadEtfs()
        case .signal where signals.isEmpty: await loadSignals()
        default: break
        }
    }

    private func loadMarket() async {
        do {
            let result = try await APIClient.shared.send(.fundFlowMarket(), as: MarketFundFlow.self)
            market = result
            tradeDate = result.tradeDate
        } catch {
            // 快照失败静默：列表仍可用，卡片回落为空态
        }
    }

    private func loadSectors() async {
        do {
            let result = try await APIClient.shared.send(
                .fundFlowSector(limit: 100), as: SectorFundFlowListResponse.self
            )
            sectors = result.items
        } catch let error as APIError {
            if sectors.isEmpty { state = .failed(error.userMessage) }
        } catch {
            if sectors.isEmpty { state = .failed("加载失败，请稍后重试") }
        }
    }

    private func loadEtfs() async {
        do {
            let result = try await APIClient.shared.send(
                .fundFlowETF(limit: 100), as: EtfFundFlowListResponse.self
            )
            etfs = result.items
        } catch {
            if etfs.isEmpty && sectors.isEmpty { state = .failed("加载失败，请稍后重试") }
        }
    }

    private func loadSignals() async {
        do {
            let result = try await APIClient.shared.send(
                .fundFlowSignals(limit: 50), as: FlowSignalListResponse.self
            )
            signals = result.items
        } catch {
            // 信号为空不视为整页失败
        }
    }
}
