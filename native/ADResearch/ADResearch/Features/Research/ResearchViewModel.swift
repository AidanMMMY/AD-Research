import Foundation

/// 研究笔记 ViewModel：当前用户的 AI 研究笔记列表。
///
/// 契约（web/src/api/research.ts + app/api/v1/research.py）：
/// GET /research/notes?note_type=&limit=，响应为数组（无分页包装，上限 50）。
/// 后端 AI 未配置时返回 503，按普通错误态展示后端 detail 文案。
@MainActor
@Observable
final class ResearchViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    /// 笔记类型筛选（nil = 全部）
    var noteType: String? = nil {
        didSet {
            guard noteType != oldValue else { return }
            Task { await load() }
        }
    }

    private(set) var notes: [ResearchNote] = []
    private(set) var state: LoadState = .idle

    /// 筛选选项（对齐 web ResearchNotes 页 NOTE_TYPE_OPTIONS）
    static let noteTypeOptions: [(key: String, label: String)] = [
        ("daily_summary", "日报"),
        ("weekly_review", "周报"),
        ("earnings_reaction", "财报反应"),
        ("earnings_preview", "财报前瞻"),
    ]

    func loadIfNeeded() async {
        guard state == .idle else { return }
        await load()
    }

    func load() async {
        state = .loading
        do {
            notes = try await APIClient.shared.send(.researchNotes(noteType: noteType, limit: 50))
            state = .loaded
        } catch {
            state = .failed(DigestViewModel.describe(error))
        }
    }
}
