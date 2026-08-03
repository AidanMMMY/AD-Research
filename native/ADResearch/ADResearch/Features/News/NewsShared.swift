import SwiftUI

// MARK: - 资讯展示辅助（标签映射与小组件，对齐 web NewsCard 语义）

/// 事件分类中文标签（对齐 web NewsCard EVENT_CATEGORY_LABELS）
enum NewsLabels {
    static let eventCategory: [String: String] = [
        "geopolitics": "地缘", "central_bank": "央行", "election": "选举",
        "trade_war": "贸易战", "sanction": "制裁", "earnings": "财报",
        "m&a": "并购", "product": "产品", "macro": "宏观",
        "regulation": "监管", "guidance": "指引", "analyst": "分析师",
        "legal": "法律", "rumor": "传闻", "other": "其他",
    ]

    static func categoryLabel(_ value: String?) -> String? {
        guard let value, !value.isEmpty else { return nil }
        return eventCategory[value] ?? value
    }

    static func sentimentLabel(_ label: SentimentLabel?) -> String? {
        switch label {
        case .positive: return "偏多"
        case .negative: return "偏空"
        case .neutral: return "中性"
        case nil: return nil
        }
    }

    static func sentimentColor(_ label: SentimentLabel?) -> Color {
        switch label {
        case .positive: return AppTheme.Colors.rise
        case .negative: return AppTheme.Colors.fall
        default: return AppTheme.Colors.textMuted
        }
    }

    static func marketLabel(_ market: NewsMarket) -> String {
        switch market {
        case .cnA: return "A股"
        case .us: return "美股"
        case .crypto: return "加密"
        case .global: return "全球"
        }
    }
}

/// 事件分类 chip
struct NewsCategoryChip: View {
    let category: String?

    var body: some View {
        if let label = NewsLabels.categoryLabel(category) {
            Text(label)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.accent)
                .padding(.horizontal, AppTheme.Spacing.sm)
                .padding(.vertical, AppTheme.Spacing.xxs)
                .background(Capsule(style: .continuous).fill(AppTheme.Colors.accentSoft))
        }
    }
}

/// 情绪 chip（红=偏多 / 绿=偏空，与涨跌同色方便扫读）
struct NewsSentimentChip: View {
    let label: SentimentLabel?

    var body: some View {
        if let text = NewsLabels.sentimentLabel(label) {
            let color = NewsLabels.sentimentColor(label)
            Text(text)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(color)
                .padding(.horizontal, AppTheme.Spacing.sm)
                .padding(.vertical, AppTheme.Spacing.xxs)
                .background(Capsule(style: .continuous).fill(color.opacity(0.10)))
        }
    }
}

/// 重要性星级（1-5，仅展示 ≥3 的，低重要性不刷屏）
struct NewsImportanceStars: View {
    let importance: Int?

    var body: some View {
        if let importance, importance >= 3 {
            HStack(spacing: 1) {
                ForEach(0..<importance, id: \.self) { _ in
                    Image(systemName: "star.fill")
                        .font(.system(size: 8))
                }
            }
            .foregroundStyle(AppTheme.Colors.warning)
            .accessibilityLabel("重要性 \(importance) 星")
        }
    }
}
