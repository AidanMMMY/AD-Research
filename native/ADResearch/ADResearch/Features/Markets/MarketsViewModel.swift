import Foundation

/// 行情总览 ViewModel：加密行情列表（实时价 enrich）。
///
/// 契约：GET /crypto（CryptoListResponse）。
/// 注意：后端接受但不应用 sort_by/sort_order（app/api/v1/crypto.py
/// 未透传给查询），排序在客户端完成。
@MainActor
@Observable
final class MarketsViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    enum SortOption: String, CaseIterable, Identifiable {
        case change
        case price
        case volume
        case name

        var id: String { rawValue }

        var label: String {
            switch self {
            case .change: return "24h 涨跌"
            case .price: return "价格"
            case .volume: return "24h 成交量"
            case .name: return "名称"
            }
        }
    }

    var sort: SortOption = .change

    private(set) var items: [CryptoInfo] = []
    private(set) var state: LoadState = .idle
    /// 列表快照的实时价更新时间（取各项最新）
    private(set) var lastUpdated: String?

    /// 客户端排序后的展示序列
    var sortedItems: [CryptoInfo] {
        switch sort {
        case .change:
            return items.sorted { ($0.changePct ?? -.infinity) > ($1.changePct ?? -.infinity) }
        case .price:
            return items.sorted { ($0.price ?? -.infinity) > ($1.price ?? -.infinity) }
        case .volume:
            return items.sorted { ($0.volume24h ?? -.infinity) > ($1.volume24h ?? -.infinity) }
        case .name:
            return items.sorted { $0.displayName.localizedCompare($1.displayName) == .orderedAscending }
        }
    }

    func loadIfNeeded() async {
        guard state == .idle else { return }
        await reload()
    }

    func reload() async {
        state = .loading
        do {
            // 行情总览一屏看全：page_size 取后端上限 200
            let response: CryptoListResponse = try await APIClient.shared.send(
                .cryptoList(page: 1, pageSize: 200)
            )
            items = response.items
            lastUpdated = response.items.compactMap(\.lastUpdated).max()
            state = .loaded
        } catch {
            state = .failed(DigestViewModel.describe(error))
        }
    }

    /// 静默刷新（30s 自动轮询用）：已加载时不回退骨架态、不打断滚动位置；
    /// 失败保留旧数据（仅未加载过时落错误态）。
    func refreshQuietly() async {
        do {
            let response: CryptoListResponse = try await APIClient.shared.send(
                .cryptoList(page: 1, pageSize: 200)
            )
            items = response.items
            lastUpdated = response.items.compactMap(\.lastUpdated).max()
            state = .loaded
        } catch {
            if state != .loaded {
                state = .failed(DigestViewModel.describe(error))
            }
        }
    }
}
