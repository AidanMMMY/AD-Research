import Foundation

// MARK: - 研究笔记模型（逐字段对齐 web/src/api/research.ts 的 ResearchNote，
// 后端 app/api/v1/research.py NoteResponse 复核一致）

/// AI 研究笔记（GET /research/notes 列表项，响应为数组、无分页包装）。
/// ``content`` 为 Markdown 正文，详情页用 ``MarkdownRenderer`` 原生渲染。
struct ResearchNote: Decodable, Sendable, Identifiable, Equatable {
    let id: Int
    let instrumentCode: String
    let name: String?
    let nameZh: String?
    /// daily_summary / weekly_review / earnings_reaction / earnings_preview
    let noteType: String
    let content: String
    let summary: String?
    /// bullish / bearish / neutral
    let sentiment: String?
    /// 0-100 置信度
    let confidence: Int?
    let generatedAt: String?
    let createdAt: String?

    /// 显示用标的名称（中文优先，退化为代码）
    var displayName: String {
        if let nameZh, !nameZh.isEmpty { return nameZh }
        if let name, !name.isEmpty { return name }
        return instrumentCode
    }
}

/// 研究笔记标签映射（对齐 web ResearchNotes 页 NOTE_TYPE_OPTIONS / SENTIMENT_VARIANTS）
enum ResearchNoteLabels {
    static let noteType: [String: String] = [
        "daily_summary": "日报",
        "weekly_review": "周报",
        "earnings_reaction": "财报反应",
        "earnings_preview": "财报前瞻",
    ]

    static func noteTypeLabel(_ value: String) -> String {
        noteType[value] ?? value
    }

    static func sentimentLabel(_ value: String?) -> String? {
        switch value {
        case "bullish": return "看多"
        case "bearish": return "看空"
        case "neutral": return "中性"
        default: return nil
        }
    }
}
