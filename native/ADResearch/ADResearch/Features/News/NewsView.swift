import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

/// 资讯流：中文优先双列表 + 市场/重要性筛选 + 搜索。
///
/// iOS：单列卡片流（refreshable + 搜索防抖 + chip 筛选条）；
/// macOS：内容限宽 860 居中，搜索/筛选进 toolbar（.searchable + Menu）。
/// 点击进 ``NewsDetailView``（路由 AppRoute.newsDetail(id)）；
/// 右键/长按菜单：复制链接 / 浏览器打开原文 / 收藏（learning bookmark 端点）。
struct NewsView: View {
    @Environment(AppState.self) private var appState
    @State private var viewModel = NewsViewModel()
    @State private var searchText = ""
    @State private var searchTask: Task<Void, Never>?
    #if os(macOS)
    /// 键盘导航高亮下标（↑↓/jk 移动，Return 打开，见 ADKeyboardNavButtons）
    @State private var highlightedIndex: Int?
    #endif

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    #if os(iOS)
                    filterBar
                    #endif
                    contentList
                }
                .padding(.horizontal, AppTheme.Spacing.lg)
                .padding(.vertical, AppTheme.Spacing.md)
                #if os(macOS)
                // 桌面端全宽卡片行长难读：限宽 860 并居中
                .frame(maxWidth: 860)
                .frame(maxWidth: .infinity)
                #endif
            }
            #if os(macOS)
            .background(
                ADKeyboardNavButtons(
                    count: viewModel.items.count,
                    highlighted: $highlightedIndex
                ) { index in
                    guard viewModel.items.indices.contains(index) else { return }
                    appState.navigate(to: .news, route: .newsDetail(viewModel.items[index].id))
                }
            )
            .onChange(of: highlightedIndex) { _, newValue in
                guard let newValue, viewModel.items.indices.contains(newValue) else { return }
                withAnimation(AppTheme.Motion.fade) {
                    proxy.scrollTo(viewModel.items[newValue].id, anchor: .center)
                }
            }
            // 列表内容变化（刷新/翻页/过滤）后高亮越界即清空
            .onChange(of: viewModel.items.count) { _, newCount in
                if let highlightedIndex, highlightedIndex >= newCount {
                    self.highlightedIndex = nil
                }
            }
            #endif
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("资讯")
        #if os(macOS)
        .searchable(text: $searchText, placement: .toolbar, prompt: "搜索标题 / 正文")
        .toolbar { macFilterToolbar }
        #else
        .searchable(text: $searchText, prompt: "搜索标题 / 正文")
        #endif
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

    // MARK: - 筛选（iOS chip 条 / macOS toolbar 菜单，共用同一份 Menu 内容）

    private var filterBar: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            marketMenu
            importanceMenu
            Spacer()
        }
    }

    #if os(macOS)
    @ToolbarContentBuilder
    private var macFilterToolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            marketMenu
            importanceMenu
        }
    }
    #endif

    private var marketMenu: some View {
        Menu {
            Button { viewModel.market = nil } label: {
                selectionLabel("全部市场", selected: viewModel.market == nil)
            }
            ForEach([NewsMarket.cnA, .us, .crypto], id: \.self) { market in
                Button { viewModel.market = market } label: {
                    selectionLabel(NewsLabels.marketLabel(market), selected: viewModel.market == market)
                }
            }
        } label: {
            filterChip(viewModel.market.map(NewsLabels.marketLabel) ?? "全部市场")
        }
    }

    private var importanceMenu: some View {
        Menu {
            Button { viewModel.importanceMin = nil } label: {
                selectionLabel("全部重要性", selected: viewModel.importanceMin == nil)
            }
            ForEach([3, 4], id: \.self) { min in
                Button { viewModel.importanceMin = min } label: {
                    selectionLabel("≥ \(min) 星", selected: viewModel.importanceMin == min)
                }
            }
            Button { viewModel.importanceMin = 5 } label: {
                selectionLabel("仅 5 星", selected: viewModel.importanceMin == 5)
            }
        } label: {
            filterChip(viewModel.importanceMin.map { $0 >= 5 ? "仅 5 星" : "≥ \($0) 星" } ?? "全部重要性")
        }
    }

    @ViewBuilder
    private func selectionLabel(_ title: String, selected: Bool) -> some View {
        if selected {
            Label(title, systemImage: "checkmark")
        } else {
            Text(title)
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
                ForEach(Array(viewModel.items.enumerated()), id: \.element.id) { index, article in
                    newsCell(article, index: index)
                        .id(article.id)
                }
                if viewModel.canLoadMore {
                    HStack {
                        Spacer()
                        ProgressView()
                            .controlSize(.small)
                        Spacer()
                    }
                    .padding(.vertical, AppTheme.Spacing.sm)
                }
            }
        }
    }

    private func newsCell(_ article: NewsArticle, index: Int) -> some View {
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
                        importanceBadge(article.importance)
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
        #if os(macOS)
        .adKeyboardHighlight(highlightedIndex == index)
        #endif
        .contextMenu { cellContextMenu(article) }
        .onAppear {
            if article.id == viewModel.items.last?.id {
                Task { await viewModel.loadMore() }
            }
        }
    }

    // MARK: - 行内右键 / 长按菜单

    @ViewBuilder
    private func cellContextMenu(_ article: NewsArticle) -> some View {
        Button {
            copyLink(article)
        } label: {
            Label("复制链接", systemImage: "doc.on.doc")
        }
        Button {
            openOriginal(article)
        } label: {
            Label("在浏览器打开原文", systemImage: "safari")
        }
        Divider()
        Button {
            Task { await viewModel.toggleBookmark(article) }
        } label: {
            let bookmarked = viewModel.isBookmarked(article)
            Label(
                bookmarked ? "取消收藏" : "收藏",
                systemImage: bookmarked ? "bookmark.slash" : "bookmark"
            )
        }
    }

    private func copyLink(_ article: NewsArticle) {
        #if os(macOS)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(article.url, forType: .string)
        #else
        UIPasteboard.general.string = article.url
        #endif
    }

    private func openOriginal(_ article: NewsArticle) {
        guard let url = URL(string: article.url) else { return }
        #if os(macOS)
        NSWorkspace.shared.open(url)
        #else
        UIApplication.shared.open(url)
        #endif
    }

    /// 重要性数字徽章（★ + 数字；替代 8pt 小星星，11pt 起更易读，全页统一）
    @ViewBuilder
    private func importanceBadge(_ importance: Int?) -> some View {
        if let importance, importance >= 3 {
            HStack(spacing: 2) {
                Image(systemName: "star.fill")
                    .font(.system(size: 11))
                Text("\(importance)")
                    .font(AppTheme.Typography.caption.monospacedDigit())
            }
            .foregroundStyle(AppTheme.Colors.warning)
            .accessibilityLabel("重要性 \(importance) 星")
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
