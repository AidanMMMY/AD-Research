import Foundation

/// 组合 ViewModel：自选列表（含行情快照）+ 标的池。
///
/// 数据：GET /favorites + GET /pools + GET /market-data/snapshot（批量报价，
/// change_pct 已是百分数单位，直接喂 ``ChangeText``）。
@MainActor
@Observable
final class PortfolioViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    private(set) var favorites: [FavoriteItem] = []
    /// code → 最新快照（快照缺失的标的报价渲染「—」）
    private(set) var snapshots: [String: MarketSnapshotItem] = [:]
    private(set) var pools: [InstrumentPool] = []
    private(set) var state: LoadState = .idle
    /// 移除中的自选 code（防连点）
    private(set) var removingCodes: Set<String> = []

    func loadIfNeeded() async {
        guard state == .idle else { return }
        await load()
    }

    func load() async {
        state = .loading
        do {
            async let favoritesTask: FavoriteListResponse = APIClient.shared.send(.favoritesList())
            async let poolsTask: [InstrumentPool] = APIClient.shared.send(.poolsList)
            let (favoriteResponse, poolList) = try await (favoritesTask, poolsTask)
            favorites = favoriteResponse.items
            pools = poolList
            snapshots = try await fetchSnapshots(for: favoriteResponse.items.map(\.etfCode))
            state = .loaded
        } catch {
            state = .failed(DigestViewModel.describe(error))
        }
    }

    /// 仅刷新报价（下拉刷新时的轻量路径之外，全量 load 已足够，这里供后续复用）
    func refreshSnapshots() async {
        guard state == .loaded else { return }
        do {
            snapshots = try await fetchSnapshots(for: favorites.map(\.etfCode))
        } catch {
            // 报价刷新失败保留旧值
        }
    }

    /// 移除自选（DELETE /favorites/{code}；乐观移除，失败回滚）
    func removeFavorite(_ item: FavoriteItem) async {
        let code = item.etfCode
        guard !removingCodes.contains(code) else { return }
        removingCodes.insert(code)
        defer { removingCodes.remove(code) }

        let index = favorites.firstIndex { $0.etfCode == code }
        favorites.removeAll { $0.etfCode == code }
        do {
            let _: FavoriteToggleResponse = try await APIClient.shared.send(.favoriteRemove(code))
            snapshots.removeValue(forKey: code)
        } catch {
            if let index {
                favorites.insert(item, at: min(index, favorites.count))
            } else {
                favorites.append(item)
            }
        }
    }

    func snapshot(for code: String) -> MarketSnapshotItem? {
        snapshots[code]
    }

    // MARK: - 私有

    private func fetchSnapshots(for codes: [String]) async throws -> [String: MarketSnapshotItem] {
        guard !codes.isEmpty else { return [:] }
        let response: MarketSnapshotResponse = try await APIClient.shared.send(
            .marketSnapshot(codes: codes)
        )
        return Dictionary(response.items.map { ($0.etfCode, $0) }, uniquingKeysWith: { _, last in last })
    }
}
