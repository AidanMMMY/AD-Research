import Foundation

/// 每日研报列表 ViewModel。
///
/// 数据：GET /digest 分页列表（不含正文）+ GET /digest/latest/summary 顶部卡。
/// 契约见 ``DigestListResponse`` / ``DigestLatestSummary``。
@MainActor
@Observable
final class DigestViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    private(set) var items: [DigestListItem] = []
    private(set) var state: LoadState = .idle
    private(set) var page = 1
    private(set) var totalPages = 1
    /// 顶部「今日研报」摘要（nil = 今日未出报，显示引导空态）
    private(set) var todaySummary: DigestLatestSummary?
    private(set) var todayLoaded = false

    var canLoadMore: Bool { page < totalPages }

    func loadIfNeeded() async {
        guard state == .idle else { return }
        await load()
    }

    func load() async {
        state = .loading
        do {
            async let listTask: DigestListResponse = APIClient.shared.send(
                .digestList(page: 1, pageSize: 20)
            )
            async let summaryTask: DigestLatestSummary? = Self.fetchTodaySummary()
            let (list, summary) = try await (listTask, summaryTask)
            items = list.items
            page = list.page
            totalPages = max(list.totalPages, 1)
            todaySummary = summary
            todayLoaded = true
            state = .loaded
        } catch {
            state = .failed(Self.describe(error))
        }
    }

    /// 分页追加（列表底部 onAppear 触发）
    func loadMore() async {
        guard canLoadMore, state == .loaded else { return }
        let next = page + 1
        do {
            let list: DigestListResponse = try await APIClient.shared.send(
                .digestList(page: next, pageSize: 20)
            )
            items.append(contentsOf: list.items)
            page = list.page
            totalPages = max(list.totalPages, 1)
        } catch {
            // 分页失败不打断已加载内容，静默保留重试入口（再次滚动到底触发）
        }
    }

    /// 今日摘要 404 = 未出报（空态语义，非错误）
    private static func fetchTodaySummary() async throws -> DigestLatestSummary? {
        do {
            return try await APIClient.shared.send(.digestLatestSummary)
        } catch let error as APIError {
            if error.isNotFound { return nil }
            throw error
        }
    }

    static func describe(_ error: Error) -> String {
        if let apiError = error as? APIError {
            return apiError.userMessage
        }
        return "加载失败，请稍后重试"
    }
}

/// 单篇研报详情 ViewModel（路由：AppRoute.digestDetail(date)）。
@MainActor
@Observable
final class DigestDetailViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case notFound
        case failed(String)
    }

    let reportDate: String
    private(set) var report: DigestReport?
    private(set) var state: LoadState = .idle

    init(reportDate: String) {
        self.reportDate = reportDate
    }

    func loadIfNeeded() async {
        guard state == .idle else { return }
        await load()
    }

    func load() async {
        state = .loading
        do {
            report = try await APIClient.shared.send(.digestByDate(reportDate))
            state = .loaded
        } catch let error as APIError {
            if error.isNotFound {
                state = .notFound
            } else {
                state = .failed(DigestViewModel.describe(error))
            }
        } catch {
            state = .failed(DigestViewModel.describe(error))
        }
    }
}
