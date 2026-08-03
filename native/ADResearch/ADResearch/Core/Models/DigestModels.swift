import Foundation

// MARK: - 每日研报模型（逐字段对齐 web/src/api/digest.ts）

/// 报告生成状态：partial = 有章节降级/缺失
enum DigestStatus: String, Codable, Sendable {
    case pending
    case running
    case success
    case partial
    case failed
}

/// 单章节采集/生成状态
enum DigestSectionStatus: String, Codable, Sendable {
    case ok
    case degraded
    case failed
}

/// GET /digest 列表项（不含 content_md）
struct DigestListItem: Codable, Sendable, Identifiable {
    let id: Int
    /// YYYY-MM-DD
    let reportDate: String
    let title: String
    let status: DigestStatus
    let summaryMd: String?
    let contentChars: Int
}

/// GET /digest 分页响应
struct DigestListResponse: Decodable, Sendable {
    let items: [DigestListItem]
    let page: Int
    let pageSize: Int
    let total: Int
    let totalPages: Int
}

/// 章节元信息
struct DigestSection: Codable, Sendable {
    let key: String
    let title: String
    let status: DigestSectionStatus
    let chars: Int
    let retries: Int
}

/// 完整报告（/latest 与 /by-date 返回结构）
struct DigestReport: Codable, Sendable, Identifiable {
    let id: Int
    let reportDate: String
    let title: String
    let status: DigestStatus
    let summaryMd: String?
    let contentMd: String?
    let sectionsJson: [DigestSection]
    let llmModel: String?
    let finishedAt: String?
}

/// GET /digest/latest/summary 轻量结构（404 = 今日尚无报告 → 空态）
struct DigestLatestSummary: Codable, Sendable, Identifiable {
    let id: Int
    let reportDate: String
    let title: String
    let status: DigestStatus
    let summaryMd: String?
    let contentChars: Int
}
