import SwiftUI

/// 资讯详情：中文优先的阅读页。
///
/// 正文优先级：AI 中文译文（可切换原文）→ 抓取正文 → 引子摘要。
/// 英文文章提供「翻译全文」按钮（后端缓存，无重复 LLM 成本）。
struct NewsDetailView: View {
    @State private var viewModel: NewsDetailViewModel
    /// 双语文章的正文显示模式：true=中文译文，false=原文
    @State private var showTranslation = true

    init(articleID: Int) {
        _viewModel = State(initialValue: NewsDetailViewModel(articleID: articleID))
    }

    var body: some View {
        ScrollView {
            content
                .padding(.horizontal, AppTheme.Spacing.lg)
                .padding(.vertical, AppTheme.Spacing.md)
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("资讯详情")
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
        case .loaded:
            if let article = viewModel.article {
                articleBody(article)
            }
        }
    }

    // MARK: - 正文

    private func articleBody(_ article: NewsArticle) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            // 头部元信息
            HStack(spacing: AppTheme.Spacing.sm) {
                Text(article.source)
                Text("·")
                Text(DateFormatting.relative(article.publishedAt))
                Spacer()
                NewsImportanceStars(importance: article.importance)
            }
            .font(AppTheme.Typography.caption)
            .foregroundStyle(AppTheme.Colors.textMuted)

            // 标题（中文优先；有译文标题时原文作副题）
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text(article.displayTitle)
                    .font(AppTheme.Typography.pageTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                if article.titleZh != nil, article.titleZh != article.title {
                    Text(article.title)
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
            }

            // 标签行
            HStack(spacing: AppTheme.Spacing.sm) {
                NewsCategoryChip(category: article.eventCategory)
                NewsSentimentChip(label: article.sentimentLabel)
                Text(NewsLabels.marketLabel(article.market))
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }

            // 关联标的
            if !article.symbols.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        ForEach(article.symbols, id: \.symbol) { symbol in
                            Text(symbol.nameZh ?? symbol.name ?? symbol.symbol)
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.accent)
                                .padding(.horizontal, AppTheme.Spacing.sm)
                                .padding(.vertical, AppTheme.Spacing.xxs)
                                .background(
                                    Capsule(style: .continuous).fill(AppTheme.Colors.accentSoft)
                                )
                        }
                    }
                }
            }

            Divider().overlay(AppTheme.Colors.border)

            // 双语切换（仅英文文章且有译文时）
            if article.language == "en", viewModel.translation != nil {
                Picker("语言", selection: $showTranslation) {
                    Text("中文译文").tag(true)
                    Text("英文原文").tag(false)
                }
                .pickerStyle(.segmented)
            }

            bodyContent(article)

            // 操作行
            actionRow(article)

            if let error = viewModel.actionError {
                Text(error)
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.error)
            }

            // 原文链接
            if let url = URL(string: article.url) {
                Link(destination: url) {
                    Label("查看原文网页", systemImage: "safari")
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.accent)
                }
            }
        }
        .frame(maxWidth: 760, alignment: .leading)
        .frame(maxWidth: .infinity, alignment: .leading)
        .animation(AppTheme.Motion.fade, value: viewModel.state)
    }

    /// 正文内容（双语逻辑 + 抓取降级链）
    @ViewBuilder
    private func bodyContent(_ article: NewsArticle) -> some View {
        let original = viewModel.fetchedContent ?? article.fullContent
        let useTranslation = article.language == "en" && showTranslation && viewModel.translation != nil

        if useTranslation, let translation = viewModel.translation {
            Text(MarkdownRenderer.attributed(translation))
                .font(AppTheme.Typography.body)
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .lineSpacing(6)
                .textSelection(.enabled)
        } else if let original, !original.isEmpty {
            Text(MarkdownRenderer.attributed(original))
                .font(AppTheme.Typography.body)
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .lineSpacing(6)
                .textSelection(.enabled)
        } else if viewModel.fetchingContent {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                Text("正在抓取全文…")
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                ForEach(0..<5, id: \.self) { _ in
                    SkeletonBlock(height: 14)
                }
            }
        } else if let excerpt = article.body ?? article.summary, !excerpt.isEmpty {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                Text(excerpt)
                    .font(AppTheme.Typography.body)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineSpacing(6)
                Text("全文抓取失败时仅显示引子。点下方「重新抓取」重试。")
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
        } else {
            EmptyStateView(
                systemImage: "doc.plaintext",
                title: "暂无正文",
                description: "可尝试「重新抓取」从原文页面提取"
            )
        }
    }

    // MARK: - 操作行

    private func actionRow(_ article: NewsArticle) -> some View {
        HStack(spacing: AppTheme.Spacing.lg) {
            if article.language == "en", viewModel.translation == nil {
                Button {
                    Task { await viewModel.translate() }
                } label: {
                    Label(
                        viewModel.translating ? "翻译中…" : "翻译全文",
                        systemImage: "character.bubble"
                    )
                }
                .disabled(viewModel.translating)
            }
            Button {
                Task { await viewModel.fetchContent() }
            } label: {
                Label(
                    viewModel.fetchingContent ? "抓取中…" : "重新抓取",
                    systemImage: "arrow.clockwise"
                )
            }
            .disabled(viewModel.fetchingContent)
        }
        .font(AppTheme.Typography.callout)
        .buttonStyle(.borderless)
        .foregroundStyle(AppTheme.Colors.accent)
    }

    private var skeleton: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            SkeletonBlock(height: 10).frame(width: 180)
            SkeletonBlock(height: 26)
            SkeletonBlock(height: 26).frame(maxWidth: 300)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                ForEach(0..<6, id: \.self) { _ in
                    SkeletonBlock(height: 14)
                }
            }
        }
    }
}
