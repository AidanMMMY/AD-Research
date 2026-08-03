import Foundation

// MARK: - 资讯模型（逐字段对齐 web/src/types/news.ts）

/// 市场分区。``global`` 是前端哨兵值（M22-2），后端映射为全市场并集。
enum NewsMarket: String, Codable, Sendable {
    case cnA = "cn_a"
    case us
    case crypto
    case global
}

/// LLM 情绪标签
enum SentimentLabel: String, Codable, Sendable {
    case negative
    case neutral
    case positive
}

/// 文章提及的标的
struct NewsSymbol: Codable, Sendable, Equatable {
    let symbol: String
    let market: String?
    /// 匹配方式（ticker / name / alias）
    let matchType: String?
    /// 标的显示名（etf_info 缓存）
    let name: String?
    /// 中文显示名
    let nameZh: String?
}

/// 互动指标（ts 是索引签名，这里收敛为常用字段，多余键丢弃）
struct NewsEngagement: Codable, Sendable, Equatable {
    let likes: Double?
    let comments: Double?
    let shares: Double?
    let views: Double?
}

/// 资讯文章（``NewsArticle``，与后端 ``app/schemas/news*.py`` 对齐）
struct NewsArticle: Codable, Sendable, Identifiable {
    let id: Int
    /// 来源标识（xinhua / xueqiu / reddit…）
    let source: String
    let url: String
    let market: NewsMarket
    let language: String
    let title: String
    /// AI 中文标题（入库自动翻译；中文源恒为 null）。渲染 ``titleZh ?? title``
    let titleZh: String?
    /// AI 一句话中文摘要（≥3 重要性文章，drain 任务回填）
    let summaryZh: String?
    /// 爬虫交接的引子/摘录
    let body: String?
    /// RSS 摘要（当前与 body 同文）
    let summary: String?
    let author: String?
    /// ISO8601 发布时间（保留 String，用 DateFormatting 解析）
    let publishedAt: String
    let fetchedAt: String
    let engagement: NewsEngagement
    /// [-1, 1] 归一化情绪分
    let sentimentScore: Double?
    let sentimentLabel: SentimentLabel?
    /// [0, 1] 情绪置信度
    let sentimentConfidence: Double?
    let sentimentDrivers: [String]?
    let eventCategory: String?
    /// 重要性 1-5（5 = 市场级事件）
    let importance: Int?
    let symbols: [NewsSymbol]
    /// 清洗后的正文（本地存储；null = 从未抓取）
    let fullContent: String?
    let fullContentFetchedAt: String?
    /// 缓存的中文翻译（仅英文文章）
    let translatedZh: String?
    let translationGeneratedAt: String?
    /// AI 清洗可观测性：cleaned / skipped / failed / not_attempted / null
    let aiCleanupStatus: String?
    let aiCleanedAt: String?
    /// 当前用户收藏态（仅 /learning/* 端点返回；消费方用 ?? false）
    let bookmarked: Bool?
    /// 当前用户已读态（同上）
    let read: Bool?
    /// 源级默认难度（仅 /learning/* 端点返回）
    let difficultyDefault: String?

    /// 显示用标题（中文优先）
    var displayTitle: String { titleZh ?? title }
}

/// GET /news 分页响应
struct NewsListResponse: Decodable, Sendable {
    let items: [NewsArticle]
    let total: Int
    let page: Int
    let pageSize: Int
    let totalPages: Int
}

/// POST /news/{id}/fetch-content 响应（对齐 NewsFetchContentResponse）。
/// 端点恒不抛 5xx——Jina 错误收敛为 ``{success:false, error:...}``。
struct NewsFetchContentResponse: Decodable, Sendable {
    let success: Bool
    /// 缓存的 Markdown 正文；失败时退化为引子
    let content: String?
    let cached: Bool
    let error: String?
}

/// POST /news/{id}/translate 响应（对齐 NewsTranslateResponse）。
/// 后端强制 ``language == 'en'``（否则 400）+ 每用户每日限流（429）。
struct NewsTranslateResponse: Decodable, Sendable {
    /// 中文译文（Markdown）；命中缓存时与 ``translatedZh`` 同文
    let translation: String
    /// true = 命中缓存，无 LLM 调用
    let cached: Bool
    let tokensUsed: Int?
    let generatedAt: String?
    let sourceLanguage: String
    let targetLanguage: String
}

/// GET /news 查询参数（对齐 NewsListParams）
struct NewsListParams: Sendable {
    var market: String?
    var symbol: String?
    var source: String?
    var fromDate: String?
    var toDate: String?
    /// 全文搜索（服务端 best-effort）
    var q: String?
    var page: Int?
    var pageSize: Int?
    var importanceMin: Int?
    /// 事件分类过滤（序列化为重复查询参数 OR 语义）
    var eventCategory: [String]?

    init(
        market: String? = nil,
        symbol: String? = nil,
        source: String? = nil,
        fromDate: String? = nil,
        toDate: String? = nil,
        q: String? = nil,
        page: Int? = nil,
        pageSize: Int? = nil,
        importanceMin: Int? = nil,
        eventCategory: [String]? = nil
    ) {
        self.market = market
        self.symbol = symbol
        self.source = source
        self.fromDate = fromDate
        self.toDate = toDate
        self.q = q
        self.page = page
        self.pageSize = pageSize
        self.importanceMin = importanceMin
        self.eventCategory = eventCategory
    }
}
