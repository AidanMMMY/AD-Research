import Foundation

/// 板块轮动 ViewModel。
///
/// 契约：GET /sector-rotation（SectorRotationResponse）。
/// classification：GICS（全球默认）/ SW（申万2021一级，A股）。
@MainActor
@Observable
final class SectorsViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    enum Classification: String, CaseIterable, Identifiable {
        case gics = "GICS"
        case sw = "SW"

        var id: String { rawValue }

        var label: String {
            switch self {
            case .gics: return "GICS"
            case .sw: return "申万"
            }
        }
    }

    var classification: Classification = .sw {
        didSet { Task { await reload() } }
    }

    private(set) var sectors: [SectorPerformance] = []
    private(set) var marketAvg: SectorMarketAverage?
    private(set) var signals: [RotationSignal] = []
    private(set) var tradeDate: String?
    private(set) var state: LoadState = .idle

    /// 展示序列：按动量排名升序（1 = 最强）
    var rankedSectors: [SectorPerformance] {
        sectors.sorted { $0.momentumRank < $1.momentumRank }
    }

    func loadIfNeeded() async {
        guard state == .idle else { return }
        await reload()
    }

    func reload() async {
        state = .loading
        do {
            let response: SectorRotationResponse = try await APIClient.shared.send(
                .sectorRotation(classification: classification.rawValue)
            )
            sectors = response.sectors
            marketAvg = response.marketAvg
            signals = response.rotationSignals
            tradeDate = response.tradeDate
            state = .loaded
        } catch {
            state = .failed(DigestViewModel.describe(error))
        }
    }
}
