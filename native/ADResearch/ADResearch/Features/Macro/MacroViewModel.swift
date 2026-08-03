import Foundation

/// 宏观 ViewModel：区域分组的最新快照 + 实时全球指数。
///
/// 数据：GET /macro/latest?region=（cn/eu/us/global 四区并发）+
/// GET /macro/indices/global（实时指数，含 staleCount）。
@MainActor
@Observable
final class MacroViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    /// 区域分组（保持 cn/eu/us/global 固定顺序）
    struct RegionGroup: Identifiable {
        var id: String { region }
        let region: String
        let title: String
        var items: [MacroLatestItem]
    }

    private(set) var groups: [RegionGroup] = []
    private(set) var indices: [GlobalIndexRealtimeItem] = []
    private(set) var staleCount = 0
    private(set) var state: LoadState = .idle

    private static let regionOrder: [(String, String)] = [
        ("cn", "中国"), ("us", "美国"), ("eu", "欧洲"), ("global", "全球"),
    ]

    func loadIfNeeded() async {
        guard state == .idle else { return }
        await load()
    }

    func load() async {
        state = .loading
        do {
            // 四个区域 + 实时指数并发拉取
            try await withThrowingTaskGroup(of: RegionResult.self) { group in
                for (region, _) in Self.regionOrder {
                    group.addTask {
                        let response: MacroLatestResponse = try await APIClient.shared.send(
                            .macroLatest(region: region)
                        )
                        return .latest(region: region, items: response.items)
                    }
                }
                group.addTask {
                    let response: GlobalIndicesRealtimeResponse = try await APIClient.shared.send(
                        .macroIndicesGlobal
                    )
                    return .indices(items: response.items, stale: response.staleCount ?? 0)
                }

                var latestByRegion: [String: [MacroLatestItem]] = [:]
                var indexItems: [GlobalIndexRealtimeItem] = []
                var stale = 0
                for try await result in group {
                    switch result {
                    case .latest(let region, let items):
                        latestByRegion[region] = items
                    case .indices(let items, let staleCount):
                        indexItems = items
                        stale = staleCount
                    }
                }

                groups = Self.regionOrder.compactMap { region, title in
                    guard let items = latestByRegion[region], !items.isEmpty else { return nil }
                    return RegionGroup(region: region, title: title, items: items)
                }
                indices = indexItems
                staleCount = stale
                state = .loaded
            }
        } catch {
            state = .failed(DigestViewModel.describe(error))
        }
    }

    private enum RegionResult {
        case latest(region: String, items: [MacroLatestItem])
        case indices(items: [GlobalIndexRealtimeItem], stale: Int)
    }
}
