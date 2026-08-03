import Foundation

// MARK: - 学习中心模型（逐字段对齐 web/src/api/learning.ts，2026-08-02 契约）

/// 知识主题分类（源级映射）。ts 侧允许 ``LearningTopic | string``，
/// 这里保留 String 以防后端新增主题时解码崩（同 ``UserProfile.role`` 的处理）。
/// 中文标签见 ``LearningMeta.topicLabel(_:)``。
///
/// 已知取值：allocation / valuation / macro / industry / psychology / tools / research

/// 内容性质（flash 快讯 / deep 深度 / edu 教学）
enum LearningContentType: String, Codable, Sendable {
    case flash
    case deep
    case edu
}

/// 源级默认难度；null = 混合/不确定（消费方不渲染标签）
enum LearningDifficulty: String, Codable, Sendable {
    case beginner
    case advanced
}

/// 知识库 feed 条目：``/news`` 列表行 + content_type/topic 两个学习元数据。
///
/// 实现说明：后端返回的 JSON 就是 NewsArticle 的扁平结构外加两个键，
/// 因此用同一个 decoder 先解出完整 ``NewsArticle``，再从同一容器补解
/// learning 字段——避免逐字段复制 30+ 属性造成漂移。
struct LearningArticle: Decodable, Sendable, Identifiable {
    let article: NewsArticle
    let contentType: LearningContentType?
    /// 主题键（保留 String，ts 为 ``LearningTopic | string``）
    let topic: String?

    var id: Int { article.id }

    private enum CodingKeys: String, CodingKey {
        case contentType
        case topic
    }

    init(from decoder: Decoder) throws {
        article = try NewsArticle(from: decoder)
        let container = try decoder.container(keyedBy: CodingKeys.self)
        contentType = try container.decodeIfPresent(LearningContentType.self, forKey: .contentType)
        topic = try container.decodeIfPresent(String.self, forKey: .topic)
    }
}

/// GET /learning/feed 与 GET /learning/bookmarks 分页响应。
/// 契约只保证 ``total``；page/page_size/total_pages 为可选回显，
/// 翻页以下一页是否仍有数据（loaded < total）为准。
struct LearningFeedResponse: Decodable, Sendable {
    let items: [LearningArticle]
    let total: Int
    let page: Int?
    let pageSize: Int?
    let totalPages: Int?
}

/// GET /learning/topics 单项（主题 + 文章计数）
struct LearningTopicStat: Decodable, Sendable {
    let topic: String
    let count: Int
}

/// GET /learning/topics 响应
struct LearningTopicsResponse: Decodable, Sendable {
    let topics: [LearningTopicStat]
}

/// POST /learning/articles/{id}/bookmark 响应。
/// ``bookmarked`` 是调用后的真实状态（幂等语义在状态而非调用次数上）。
struct LearningBookmarkToggleResponse: Decodable, Sendable {
    let articleId: Int
    let bookmarked: Bool
    let bookmarkedAt: String?
}

/// POST /learning/articles/{id}/read 响应（重复标记不刷新首次时间戳）
struct LearningReadResponse: Decodable, Sendable {
    let articleId: Int
    let read: Bool
    let readAt: String?
}
