import SwiftUI

/// 研究笔记详情：sheet 内阅读页（原生 Markdown 渲染，无 WebView）。
///
/// 布局参考 ``DigestDetailView``：头部元信息 → 摘要卡 → 全文 → 生成时间。
struct ResearchNoteDetailView: View {
    let note: ResearchNote
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    header
                    summaryCard
                    content
                    footer
                }
                .padding(.horizontal, AppTheme.Spacing.lg)
                .padding(.vertical, AppTheme.Spacing.md)
                .frame(maxWidth: 720, alignment: .leading) // 行长控制
                .frame(maxWidth: .infinity) // 宽屏下内容居中
            }
            .background(AppTheme.Colors.background)
            .navigationTitle(note.displayName)
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("完成") { dismiss() }
                }
            }
        }
        #if os(macOS)
        .frame(minWidth: 560, minHeight: 480)
        #endif
    }

    // MARK: - 头部

    private var header: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Text(ResearchNoteLabels.noteTypeLabel(note.noteType))
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.accent)
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, AppTheme.Spacing.xxs)
                    .background(Capsule(style: .continuous).fill(AppTheme.Colors.accentSoft))
                if let label = ResearchNoteLabels.sentimentLabel(note.sentiment) {
                    let color: Color = {
                        switch note.sentiment {
                        case "bullish": return AppTheme.Colors.rise
                        case "bearish": return AppTheme.Colors.fall
                        default: return AppTheme.Colors.textMuted
                        }
                    }()
                    Text(label)
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(color)
                        .padding(.horizontal, AppTheme.Spacing.sm)
                        .padding(.vertical, AppTheme.Spacing.xxs)
                        .background(Capsule(style: .continuous).fill(color.opacity(0.10)))
                }
                Spacer()
                if let confidence = note.confidence {
                    Text("置信度 \(confidence)%")
                        .font(AppTheme.Typography.caption.monospacedDigit())
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
            }
            Text(note.displayName)
                .font(AppTheme.Typography.pageTitle)
                .foregroundStyle(AppTheme.Colors.textPrimary)
            Text(note.instrumentCode)
                .font(AppTheme.Typography.caption.monospacedDigit())
                .foregroundStyle(AppTheme.Colors.textMuted)
        }
    }

    // MARK: - 摘要卡

    @ViewBuilder
    private var summaryCard: some View {
        if let summary = note.summary?.trimmingCharacters(in: .whitespacesAndNewlines),
           !summary.isEmpty {
            ADCard(padding: AppTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    Label("摘要", systemImage: "text.quote")
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.accent)
                    Text(MarkdownRenderer.attributed(summary))
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                }
            }
        }
    }

    // MARK: - 全文

    private var content: some View {
        MarkdownBlockView(text: note.content)
    }

    // MARK: - 尾注

    @ViewBuilder
    private var footer: some View {
        if let generatedAt = note.generatedAt, let date = DateFormatting.parse(generatedAt) {
            Text("生成于 \(DateFormatting.formatDateTime(date))")
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
        }
    }
}
