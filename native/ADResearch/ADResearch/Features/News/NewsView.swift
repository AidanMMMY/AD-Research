import SwiftUI

/// 资讯流：中文优先双列表 + 市场/重要性筛选 + 搜索。
///
/// iOS：单列卡片流（refreshable + 搜索防抖）；macOS：同构，更宽行长。
/// 点击进 ``NewsDetailView``（路由 AppRoute.newsDetail(id)）。
struct NewsView: View {
    @Environment(AppState.self) private var appState
    @State private var viewModel = NewsViewModel()
    @State private var searchText = ""
    @State private var searchTask: Task<Void, Never>?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                filterBar
                contentList
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.md)
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("资讯")
        .refreshable {
            await viewModel.reload()
        }
        .task {
            await viewModel.loadIfNeeded()
        }
        .onChange(of: searchText) { _, newValue in
            // 300ms 防抖：输入停止后再发请求
            searchTask?.cancel()
            searchTask = Task {
                try? await Task.sleep(nanoseconds: 300_000_000)
                guard !Task.isCancelled else { return }
                await MainActor.run { viewModel.query = newValue.trimmingCharacters(in: .whitespaces) }
            }
        }
        #if os(macOS)
        .onReceive(NotificationCenter.default.publisher(for: .adRefreshRequested)) { _ in
            Task { await viewModel.reload() }
        }
        #endif
    }

    // MARK: - 筛选条

    private var filterBar: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(AppTheme.Colors.textMuted)
                TextField("搜索标题 / 正文", text: $searchText)
                    .textFieldStyle(.plain)
                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(AppTheme.Colors.textMuted)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(
                RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                    .fill(AppTheme.Colors.surface)
            )

            HStack(spacing: AppTheme.Spacing.sm) {
                marketMenu
                importanceMenu
                Spacer()
            }
        }
    }

    private var marketMenu: some View {
        Menu {
            Button("全部市场") { viewModel.market = nil }
            ForEach([NewsMarket.cnA, .us, .crypto], id: \.self) { market in
                Button(NewsLabels.marketLabel(market)) { viewModel.market = market }
            }
        } label: {
            filterChip(viewModel.market.map(NewsLabels.marketLabel) ?? "全部市场")
        }
    }

    private var importanceMenu: some View {
        Menu {
            Button("全部重要性") { viewModel.importanceMin = nil }
            Button("≥ 3 星") { viewModel.importanceMin = 3 }
            Button("≥ 4 星") { viewModel.importanceMin = 4 }
            Button("仅 5 星") { viewModel.importanceMin = 5 }
        } label: {
            filterChip(viewModel.importanceMin.map { "≥ \($0) 星" } ?? "全部重要性")
        }
    }

    private func filterChip(_ title: String) -> some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            Text(title).font(AppTheme.Typography.caption)
            Image(systemName: "chevron.down").font(.system(size: 9))
        }
        .foregroundStyle(AppTheme.Colors.textSecondary)
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
        .background(Capsule(style: .continuous).fill(AppTheme.Colors.surface))
    }

    // MARK: - 列表

    @ViewBuilder
    private var contentList: some View {
        switch viewModel.state {
        case .idle, .loading:
            skeleton
        case .failed(let message):
            LoadErrorView(message: message) {
                Task { await viewModel.reload() }
            }
        case .loaded:
            if viewModel.items.isEmpty {
                EmptyStateView(
                    systemImage: "newspaper",
                    title: "没有匹配的资讯",
                    description: "换个筛选条件或搜索词试试"
                )
            } else {
                ForEach(viewModel.items) { article in
                    newsCell(article)
                }
                if viewModel.canLoadMore {
                    HStack {
                        Spacer()
                        SkeletonBlock(height: 10).frame(width: 120)
                        Spacer()
                    }
                }
            }
        }
    }

    private func newsCell(_ article: NewsArticle) -> some View {
        Button {
            Haptics.selection()
            appState.navigate(to: .news, route: .newsDetail(article.id))
        } label: {
            ADCard(padding: AppTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    // 元信息行：来源 · 相对时间 · 重要性
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Text(article.source)
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textMuted)
                        Text("·")
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textMuted)
                        Text(DateFormatting.relative(article.publishedAt))
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textMuted)
                        Spacer()
                        NewsImportanceStars(importance: article.importance)
                    }
                    // 标题（中文优先）
                    Text(article.displayTitle)
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .multilineTextAlignment(.leading)
                        .lineLimit(2)
                    // 摘要（AI 一句话中文摘要优先，其次引子）
                    if let snippet = snippet(of: article) {
                        Text(snippet)
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                    }
                    // 标签行
                    HStack(spacing: AppTheme.Spacing.sm) {
                        NewsCategoryChip(category: article.eventCategory)
                        NewsSentimentChip(label: article.sentimentLabel)
                        Spacer()
                        if !article.symbols.isEmpty {
                            Text(article.symbols.prefix(2).map { $0.nameZh ?? $0.name ?? $0.symbol }.joined(separator: "、"))
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.textMuted)
                                .lineLimit(1)
                        }
                    }
                }
            }
        }
        .buttonStyle(.plain)
        .onAppear {
            if article.id == viewModel.items.last?.id {
                Task { await viewModel.loadMore() }
            }
        }
    }

    private func snippet(of article: NewsArticle) -> String? {
        let raw = article.summaryZh ?? article.body ?? article.summary
        guard let raw else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private var skeleton: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            ForEach(0..<4, id: \.self) { _ in
                ADCard(padding: AppTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        SkeletonBlock(height: 10).frame(width: 160)
                        SkeletonBlock(height: 16)
                        SkeletonBlock(height: 12).frame(maxWidth: 280)
                    }
                }
            }
        }
    }
}

#Preview {
    NavigationStack {
        NewsView()
            .environment(AppState())
    }
}
