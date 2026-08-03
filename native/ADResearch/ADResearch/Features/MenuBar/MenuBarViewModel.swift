#if os(macOS)
import Foundation

/// 菜单栏行情 widget ViewModel（macOS MenuBarExtra）。
///
/// 契约：GET /macro/indices/global（GlobalIndicesRealtimeResponse，
/// 单项失败后端跳过、响应恒 200）。未登录/网络失败 → 静默空态「登录后查看」。
@MainActor
@Observable
final class MenuBarViewModel {
    struct Ticker: Identifiable, Equatable {
        var id: String { code }
        let code: String
        let title: String
        var value: Double?
        /// 百分数（1.23 = +1.23%）
        var changePct: Double?
    }

    /// 菜单栏常驻展示的六个代码（与 Dashboard 脉搏同口径）
    private static let watchList: [(code: String, title: String)] = [
        ("global_sp500", "标普"),
        ("global_nasdaq", "纳指"),
        ("global_shcomp", "上证"),
        ("global_hsi", "恒生"),
        ("global_n225", "日经"),
    ]

    private(set) var tickers: [Ticker]
    private(set) var lastUpdated: Date?
    private(set) var isLoading = false
    private(set) var hasData = false

    init() {
        tickers = Self.watchList.map { Ticker(code: $0.code, title: $0.title) }
    }

    /// 菜单栏标题用：标普涨跌幅（无数据 → nil，label 只显图标）
    var headlineChangePct: Double? {
        tickers.first(where: { $0.code == "global_sp500" })?.changePct
    }

    func refresh() async {
        if !hasData { isLoading = true }
        defer { isLoading = false }
        guard let response = try? await APIClient.shared.send(
            .macroIndicesGlobal, as: GlobalIndicesRealtimeResponse.self
        ) else { return }
        let lookup = Dictionary(
            response.items.compactMap { item -> (String, GlobalIndexRealtimeItem)? in
                guard item.value != nil else { return nil }
                return (item.code, item)
            },
            uniquingKeysWith: { first, _ in first }
        )
        tickers = Self.watchList.map { watch in
            let entry = lookup[watch.code]
            return Ticker(
                code: watch.code,
                title: watch.title,
                value: entry?.value ?? nil,
                changePct: entry?.changePct ?? nil
            )
        }
        hasData = tickers.contains { $0.value != nil }
        lastUpdated = Date()
    }

    /// 60s 自动刷新循环（MenuBarExtra window 样式在打开时才渲染，
    /// 但 label 常驻——保持后台轻量刷新让 label 数字不陈旧）
    func startAutoRefresh() async {
        await refresh()
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(60))
            guard !Task.isCancelled else { return }
            await refresh()
        }
    }
}
#endif
