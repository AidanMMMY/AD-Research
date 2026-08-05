import SwiftUI

/// 研报详情：移动优先的长文阅读页。
///
/// 结构：标题/日期/状态 → 摘要卡 → 章节元信息（降级章节标注）→ 全文
/// （原生 AttributedString Markdown 渲染，无 WebView）。
struct DigestDetailView: View {
    @State private var viewModel: DigestDetailViewModel

    init(reportDate: String) {
        _viewModel = State(initialValue: DigestDetailViewModel(reportDate: reportDate))
    }

    var body: some View {
        ScrollView {
            content
                .padding(.horizontal, AppTheme.Spacing.lg)
                .padding(.vertical, AppTheme.Spacing.md)
        }
        .background(AppTheme.Colors.background)
        .navigationTitle(viewModel.reportDate)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task {
            await viewModel.loadIfNeeded()
        }
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .idle, .loading:
            skeleton
        case .failed(let message):
            LoadErrorView(message: message) {
                Task { await viewModel.load() }
            }
        case .notFound:
            EmptyStateView(
                systemImage: "doc.questionmark",
                title: "这一天没有研报",
                description: "每日研报自 2026-08-03 起每日 06:30 发布"
            )
        case .loaded:
            if let report = viewModel.report {
                reportBody(report)
            }
        }
    }

    // MARK: - 正文

    private func reportBody(_ report: DigestReport) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            // 头部
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(alignment: .firstTextBaseline) {
                    Text(report.reportDate)
                        .font(AppTheme.Typography.caption.monospacedDigit())
                        .foregroundStyle(AppTheme.Colors.textMuted)
                    if report.status == .partial {
                        partialBadge
                    }
                    Spacer()
                    if let model = report.llmModel {
                        Text(model)
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textMuted)
                    }
                }
                Text(report.title)
                    .font(AppTheme.Typography.pageTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
            }

            // 摘要卡
            if let summary = report.summaryMd, !summary.isEmpty {
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

            // 章节降级提示（仅当有非 ok 章节时）
            let degraded = report.sectionsJson.filter {
                $0.status == .degraded || $0.status == .failed
            }
            if !degraded.isEmpty {
                ADCard(padding: AppTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                        Label("以下章节生成时数据降级", systemImage: "exclamationmark.triangle")
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.warning)
                        ForEach(degraded, id: \.key) { section in
                            Text("· \(section.title)")
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.textMuted)
                        }
                    }
                }
            }

            // 全文（块级 Markdown 渲染）
            if let content = report.contentMd, !content.isEmpty {
                MarkdownBlockView(text: content)
            } else {
                EmptyStateView(
                    systemImage: "doc.plaintext",
                    title: "正文为空",
                    description: "该报告未保存正文内容"
                )
            }

            if let finishedAt = report.finishedAt, let date = DateFormatting.parse(finishedAt) {
                Text("生成于 \(DateFormatting.formatDateTime(date))")
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
        }
        .frame(maxWidth: 720, alignment: .leading) // 行长控制，对齐 web 阅读页 720px
        .frame(maxWidth: .infinity) // 宽屏下内容居中，iPhone 自然全宽
        .animation(AppTheme.Motion.fade, value: viewModel.state)
    }

    private var partialBadge: some View {
        Text("部分降级")
            .font(AppTheme.Typography.caption)
            .foregroundStyle(AppTheme.Colors.warning)
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, AppTheme.Spacing.xxs)
            .background(Capsule(style: .continuous).fill(AppTheme.Colors.warning.opacity(0.12)))
    }

    private var skeleton: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            SkeletonBlock(height: 12).frame(width: 140)
            SkeletonBlock(height: 28)
            ADCard(padding: AppTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    SkeletonBlock(height: 12)
                    SkeletonBlock(height: 12)
                    SkeletonBlock(height: 12).frame(maxWidth: 260)
                }
            }
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                ForEach(0..<6, id: \.self) { _ in
                    SkeletonBlock(height: 14)
                }
            }
        }
    }
}
