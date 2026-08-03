import Foundation

/// 学习中心 ViewModel：知识 feed（推荐）+ 我的收藏，双 tab 共享状态机。
///
/// 契约（web/src/api/learning.ts，2026-08-02）：
/// - GET /learning/feed：服务端按 importance 优先排序，客户端禁止重排
/// - POST bookmark 为状态切换，响应的 ``bookmarked`` 是调用后真实状态
/// - POST read 幂等，重复调用不刷新首次时间戳
/// - 翻页以「已加载 < total」为准（total_pages 为可选回显）
@MainActor
@Observable
final class LearningViewModel {
    enum Tab: String, CaseIterable, Identifiable, Sendable {
        case recommended
        case bookmarks

        var id: String { rawValue }

        var title: String {
            switch self {
            case .recommended: return "推荐"
            case .bookmarks: return "我的收藏"
            }
        }
    }

    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    /// 当前 tab（切换时按需加载对应列表）
    var tab: Tab = .recommended {
        didSet {
            guard tab != oldValue else { return }
            Task { await loadCurrentIfNeeded() }
        }
    }

    /// 主题筛选（nil = 全部；仅推荐 tab 生效）
    var topic: String? = nil {
        didSet {
            guard topic != oldValue else { return }
            Task { await reloadRecommended() }
        }
    }

    // 推荐 feed
    private(set) var feedItems: [LearningArticle] = []
    private(set) var feedState: LoadState = .idle
    private(set) var feedPage = 1
    private(set) var feedTotal = 0

    // 我的收藏
    private(set) var bookmarkItems: [LearningArticle] = []
    private(set) var bookmarkState: LoadState = .idle
    private(set) var bookmarkPage = 1
    private(set) var bookmarkTotal = 0

    /// 主题计数（chip 条）
    private(set) var topics: [LearningTopicStat] = []

    /// 收藏/已读本地覆盖（article 是 let struct，操作结果就地覆盖：
    /// key = article id，value = 最新真实状态）
    private(set) var bookmarkOverrides: [Int: Bool] = [:]
    private(set) var readOverrides: [Int: Bool] = [:]
    /// 收藏切换进行中（防连点）
    private(set) var bookmarkingIDs: Set<Int> = []

    // MARK: - 展示辅助

    func isBookmarked(_ item: LearningArticle) -> Bool {
        bookmarkOverrides[item.id] ?? item.article.bookmarked ?? false
    }

    func isRead(_ item: LearningArticle) -> Bool {
        readOverrides[item.id] ?? item.article.read ?? false
    }

    var canLoadMoreFeed: Bool { feedItems.count < feedTotal }
    var canLoadMoreBookmarks: Bool { bookmarkItems.count < bookmarkTotal }

    // MARK: - 加载

    func loadIfNeeded() async {
        async let topicsTask: Void = loadTopics()
        async let currentTask: Void = loadCurrentIfNeeded()
        _ = await (topicsTask, currentTask)
    }

    func loadCurrentIfNeeded() async {
        switch tab {
        case .recommended:
            if feedState == .idle { await reloadRecommended() }
        case .bookmarks:
            if bookmarkState == .idle { await reloadBookmarks() }
        }
    }

    func refresh() async {
        switch tab {
        case .recommended: await reloadRecommended()
        case .bookmarks: await reloadBookmarks()
        }
    }

    func reloadRecommended() async {
        feedPage = 1
        feedState = .loading
        do {
            let response = try await fetchFeed(page: 1)
            feedItems = response.items
            feedTotal = response.total
            feedState = .loaded
        } catch {
            feedState = .failed(DigestViewModel.describe(error))
        }
    }

    func loadMoreFeed() async {
        guard canLoadMoreFeed, feedState == .loaded else { return }
        let next = feedPage + 1
        do {
            let response = try await fetchFeed(page: next)
            feedItems.append(contentsOf: response.items)
            feedPage = next
            feedTotal = response.total
        } catch {
            // 分页失败保留已加载内容，滚动到底会重试
        }
    }

    func reloadBookmarks() async {
        bookmarkPage = 1
        bookmarkState = .loading
        do {
            let response = try await fetchBookmarks(page: 1)
            bookmarkItems = response.items
            bookmarkTotal = response.total
            bookmarkState = .loaded
        } catch {
            bookmarkState = .failed(DigestViewModel.describe(error))
        }
    }

    func loadMoreBookmarks() async {
        guard canLoadMoreBookmarks, bookmarkState == .loaded else { return }
        let next = bookmarkPage + 1
        do {
            let response = try await fetchBookmarks(page: next)
            bookmarkItems.append(contentsOf: response.items)
            bookmarkPage = next
            bookmarkTotal = response.total
        } catch {
            // 同上，静默保留重试入口
        }
    }

    // MARK: - 操作

    /// 收藏切换（POST /learning/articles/{id}/bookmark）。
    /// 以响应的 ``bookmarked`` 为真实状态；收藏 tab 内取消收藏就地把行移除。
    func toggleBookmark(_ item: LearningArticle) async {
        let id = item.id
        guard !bookmarkingIDs.contains(id) else { return }
        bookmarkingIDs.insert(id)
        defer { bookmarkingIDs.remove(id) }
        do {
            let response: LearningBookmarkToggleResponse = try await APIClient.shared.send(
                .learningToggleBookmark(id)
            )
            bookmarkOverrides[id] = response.bookmarked
            if !response.bookmarked {
                bookmarkItems.removeAll { $0.id == id }
                bookmarkTotal = max(bookmarkTotal - 1, bookmarkItems.count)
            }
        } catch {
            // 操作失败不打断浏览，状态保持原样
        }
    }

    /// 标记已读（POST read，幂等；进入详情时调用一次）
    func markRead(_ item: LearningArticle) async {
        let id = item.id
        guard !isRead(item) else { return }
        readOverrides[id] = true
        do {
            let _: LearningReadResponse = try await APIClient.shared.send(.learningMarkRead(id))
        } catch {
            // 已读标记失败回滚覆盖，下次进入重试
            readOverrides.removeValue(forKey: id)
        }
    }

    // MARK: - 私有

    private func loadTopics() async {
        do {
            let response: LearningTopicsResponse = try await APIClient.shared.send(.learningTopics)
            topics = response.topics
        } catch {
            // 主题条失败不阻塞主列表
        }
    }

    private func fetchFeed(page: Int) async throws -> LearningFeedResponse {
        try await APIClient.shared.send(.learningFeed(topic: topic, page: page, pageSize: 20))
    }

    private func fetchBookmarks(page: Int) async throws -> LearningFeedResponse {
        try await APIClient.shared.send(.learningBookmarks(page: page, pageSize: 20))
    }
}

/// 学习元数据标签（对齐 web learning.ts LEARNING_TOPIC_LABELS /
/// LEARNING_TOPIC_ORDER 与难度/内容性质枚举）
enum LearningMeta {
    static let topicLabels: [String: String] = [
        "allocation": "资产配置",
        "valuation": "估值方法",
        "macro": "宏观入门",
        "industry": "行业研究",
        "psychology": "交易心理",
        "tools": "工具教程",
        "research": "深度研究",
    ]

    /// chip 条固定展示顺序
    static let topicOrder: [String] = [
        "allocation", "valuation", "macro", "industry", "psychology", "tools", "research",
    ]

    static func topicLabel(_ key: String?) -> String? {
        guard let key, !key.isEmpty else { return nil }
        return topicLabels[key] ?? key
    }

    /// 难度标签（difficultyDefault 为 String?，null/未知不渲染）
    static func difficultyLabel(_ value: String?) -> String? {
        switch value {
        case LearningDifficulty.beginner.rawValue: return "入门"
        case LearningDifficulty.advanced.rawValue: return "进阶"
        default: return nil
        }
    }

    /// 内容性质标签
    static func contentTypeLabel(_ type: LearningContentType?) -> String? {
        switch type {
        case .flash: return "快讯"
        case .deep: return "深度"
        case .edu: return "教学"
        case nil: return nil
        }
    }
}
