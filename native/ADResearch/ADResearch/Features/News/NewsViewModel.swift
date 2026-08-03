import Foundation

/// 资讯流 ViewModel：筛选（市场/重要性/搜索）+ 分页。
///
/// 契约：GET /news（NewsListParams → NewsListResponse）。
/// 搜索防抖在 View 层（.onChange + Task.sleep）做，VM 只管状态与请求。
@MainActor
@Observable
final class NewsViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    /// 市场筛选（nil = 全部）
    var market: NewsMarket? = nil {
        didSet { Task { await reload() } }
    }
    /// 重要性下限（nil = 全部；3/4/5 常用档）
    var importanceMin: Int? = nil {
        didSet { Task { await reload() } }
    }
    /// 搜索词（View 层防抖后赋值）
    var query: String = "" {
        didSet { Task { await reload() } }
    }

    private(set) var items: [NewsArticle] = []
    private(set) var state: LoadState = .idle
    private(set) var page = 1
    private(set) var totalPages = 1

    /// 收藏状态（会话内记忆；POST /learning/articles/{id}/bookmark 幂等切换，
    /// 响应的 bookmarked 是调用后真实状态）
    private(set) var bookmarkedIDs: Set<Int> = []
    private var bookmarkingIDs: Set<Int> = []

    var canLoadMore: Bool { page < totalPages }

    func isBookmarked(_ article: NewsArticle) -> Bool {
        bookmarkedIDs.contains(article.id)
    }

    /// 切换收藏（走 learning bookmark 端点；失败不打断浏览，保持原状态）
    func toggleBookmark(_ article: NewsArticle) async {
        let id = article.id
        guard !bookmarkingIDs.contains(id) else { return }
        bookmarkingIDs.insert(id)
        defer { bookmarkingIDs.remove(id) }
        do {
            let response: LearningBookmarkToggleResponse = try await APIClient.shared.send(
                .learningToggleBookmark(id)
            )
            if response.bookmarked {
                bookmarkedIDs.insert(id)
            } else {
                bookmarkedIDs.remove(id)
            }
        } catch {
            // 操作失败不打断浏览，状态保持原样
        }
    }

    func loadIfNeeded() async {
        guard state == .idle else { return }
        await reload()
    }

    func reload() async {
        page = 1
        state = .loading
        do {
            let response = try await fetch(page: 1)
            items = response.items
            totalPages = max(response.totalPages, 1)
            state = .loaded
        } catch {
            state = .failed(DigestViewModel.describe(error))
        }
    }

    func loadMore() async {
        guard canLoadMore, state == .loaded else { return }
        let next = page + 1
        do {
            let response = try await fetch(page: next)
            items.append(contentsOf: response.items)
            page = response.page
            totalPages = max(response.totalPages, 1)
        } catch {
            // 分页失败保留已加载内容，滚动到底会重试
        }
    }

    private func fetch(page: Int) async throws -> NewsListResponse {
        let params = NewsListParams(
            market: market?.rawValue,
            q: query.isEmpty ? nil : query,
            page: page,
            pageSize: 20,
            importanceMin: importanceMin
        )
        return try await APIClient.shared.send(.newsList(params))
    }
}

/// 资讯详情 ViewModel：文章本体 + 正文抓取 + 翻译。
@MainActor
@Observable
final class NewsDetailViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    let articleID: Int
    private(set) var article: NewsArticle?
    private(set) var state: LoadState = .idle
    /// 正文抓取中（fetch-content 触发 Jina）
    private(set) var fetchingContent = false
    /// 抓取到的正文（article 是 let struct 不可改，抓回的正文存这里；
    /// 展示优先级：fetchedContent ?? article.fullContent ?? body/summary）
    private(set) var fetchedContent: String?
    /// 翻译中 / 翻译结果（null=未翻译；中文文章恒 nil）
    private(set) var translating = false
    private(set) var translation: String?
    private(set) var actionError: String?

    init(articleID: Int) {
        self.articleID = articleID
    }

    func loadIfNeeded() async {
        guard state == .idle else { return }
        await load()
    }

    func load() async {
        state = .loading
        do {
            let fetched: NewsArticle = try await APIClient.shared.send(.newsDetail(articleID))
            article = fetched
            translation = fetched.translatedZh
            state = .loaded
            // 无正文时自动触发一次抓取（fetch-content 幂等，有缓存直接返回）
            if (fetched.fullContent ?? "").isEmpty {
                await fetchContent()
            }
        } catch {
            state = .failed(DigestViewModel.describe(error))
        }
    }

    /// 抓取/刷新正文（POST /news/{id}/fetch-content，恒不抛 5xx）
    func fetchContent() async {
        guard !fetchingContent else { return }
        fetchingContent = true
        defer { fetchingContent = false }
        do {
            let response: NewsFetchContentResponse = try await APIClient.shared.send(
                .newsFetchContent(articleID)
            )
            if response.success, let content = response.content {
                fetchedContent = content
            } else if let error = response.error {
                actionError = error
            }
        } catch {
            actionError = DigestViewModel.describe(error)
        }
    }

    /// 翻译正文（仅英文文章；POST /news/{id}/translate）
    func translate() async {
        guard !translating, article?.language == "en" else { return }
        translating = true
        defer { translating = false }
        do {
            let response: NewsTranslateResponse = try await APIClient.shared.send(
                .newsTranslate(articleID)
            )
            translation = response.translation
        } catch {
            actionError = DigestViewModel.describe(error)
        }
    }
}
