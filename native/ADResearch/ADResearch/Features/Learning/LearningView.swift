import SwiftUI

/// 学习中心：知识 feed（推荐 / 我的收藏 双 tab）。
///
/// - 推荐：主题 chip 条（GET /learning/topics 计数）+ importance 优先 feed
///   （服务端排序，客户端不重排）
/// - 卡片左滑（iOS）/ 右键菜单（macOS）切换收藏；已读文章视觉降权
/// - 点按进入资讯详情（AppRoute.newsDetail），进入即幂等标记已读
struct LearningView: View {
    @State private var viewModel = LearningViewModel()

    var body: some View {
        @Bindable var viewModel = viewModel

        VStack(spacing: 0) {
            Picker("学习", selection: $viewModel.tab) {
                ForEach(LearningViewModel.Tab.allCases) { tab in
                    Text(tab.title).tag(tab)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.sm)

            if viewModel.tab == .recommended {
                topicChipStrip
            }

            contentList
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("学习中心")
        .task {
            await viewModel.loadIfNeeded()
        }
        #if os(macOS)
        .onReceive(NotificationCenter.default.publisher(for: .adRefreshRequested)) { _ in
            Task { await viewModel.refresh() }
        }
        #endif
    }

    // MARK: - 主题 chip 条

    private var topicChipStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppTheme.Spacing.sm) {
                topicChip(key: nil, label: "全部", count: nil)
                ForEach(orderedTopics, id: \.topic) { stat in
                    topicChip(
                        key: stat.topic,
                        label: LearningMeta.topicLabel(stat.topic) ?? stat.topic,
                        count: stat.count
                    )
                }
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.bottom, AppTheme.Spacing.sm)
        }
    }

    /// 按 web LEARNING_TOPIC_ORDER 排序，未知主题排在最后
    private var orderedTopics: [LearningTopicStat] {
        viewModel.topics.sorted { lhs, rhs in
            let li = LearningMeta.topicOrder.firstIndex(of: lhs.topic) ?? .max
            let ri = LearningMeta.topicOrder.firstIndex(of: rhs.topic) ?? .max
            return li == ri ? lhs.count > rhs.count : li < ri
        }
    }

    private func topicChip(key: String?, label: String, count: Int?) -> some View {
        let selected = viewModel.topic == key
        return Button {
            Haptics.selection()
            viewModel.topic = key
        } label: {
            HStack(spacing: AppTheme.Spacing.xs) {
                Text(label)
                if let count {
                    Text("\(count)")
                        .monospacedDigit()
                        .foregroundStyle(selected ? AppTheme.Colors.accent : AppTheme.Colors.textMuted)
                }
            }
            .font(AppTheme.Typography.caption)
            .foregroundStyle(selected ? AppTheme.Colors.accent : AppTheme.Colors.textSecondary)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.xs)
            .background(
                Capsule(style: .continuous)
                    .fill(selected ? AppTheme.Colors.accentSoft : AppTheme.Colors.surface)
            )
        }
        .buttonStyle(.plain)
        .animation(AppTheme.Motion.standard, value: selected)
    }

    // MARK: - 列表

    @ViewBuilder
    private var contentList: some View {
        let state = viewModel.tab == .recommended ? viewModel.feedState : viewModel.bookmarkState
        switch state {
        case .idle, .loading:
            skeletonList
        case .failed(let message):
            ScrollView {
                LoadErrorView(message: message) {
                    Task { await viewModel.refresh() }
                }
                .padding(AppTheme.Spacing.lg)
            }
            .refreshable { await viewModel.refresh() }
        case .loaded:
            let items = viewModel.tab == .recommended ? viewModel.feedItems : viewModel.bookmarkItems
            if items.isEmpty {
                ScrollView {
                    emptyState
                        .padding(AppTheme.Spacing.lg)
                }
                .refreshable { await viewModel.refresh() }
            } else {
                articleList(items)
            }
        }
    }

    @ViewBuilder
    private var emptyState: some View {
        switch viewModel.tab {
        case .recommended:
            EmptyStateView(
                systemImage: "graduationcap",
                title: "暂无知识文章",
                description: "知识库文章入库后会出现在这里"
            )
        case .bookmarks:
            EmptyStateView(
                systemImage: "bookmark",
                title: "还没有收藏",
                description: "左滑文章卡片即可收藏，稍后在这里复习"
            )
        }
    }

    private func articleList(_ items: [LearningArticle]) -> some View {
        List {
            ForEach(items) { item in
                articleRow(item)
                    .listRowSeparator(.hidden)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets(
                        top: AppTheme.Spacing.xs,
                        leading: AppTheme.Spacing.lg,
                        bottom: AppTheme.Spacing.xs,
                        trailing: AppTheme.Spacing.lg
                    ))
                    .onAppear {
                        if item.id == items.last?.id {
                            Task { await loadMoreCurrent() }
                        }
                    }
            }
            if canLoadMoreCurrent {
                HStack {
                    Spacer()
                    ProgressView()
                        .controlSize(.small)
                    Spacer()
                }
                .padding(.vertical, AppTheme.Spacing.sm)
                .listRowSeparator(.hidden)
                .listRowBackground(Color.clear)
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .refreshable { await viewModel.refresh() }
    }

    private var canLoadMoreCurrent: Bool {
        viewModel.tab == .recommended ? viewModel.canLoadMoreFeed : viewModel.canLoadMoreBookmarks
    }

    private func loadMoreCurrent() async {
        if viewModel.tab == .recommended {
            await viewModel.loadMoreFeed()
        } else {
            await viewModel.loadMoreBookmarks()
        }
    }

    // MARK: - 文章卡片

    private func articleRow(_ item: LearningArticle) -> some View {
        let read = viewModel.isRead(item)
        let bookmarked = viewModel.isBookmarked(item)

        return NavigationLink(value: AppRoute.newsDetail(item.id)) {
            ADCard(padding: AppTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    // 元信息行：来源 · 相对时间 · 重要性
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Text(item.article.source)
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textMuted)
                        Text("·")
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textMuted)
                        Text(DateFormatting.relative(item.article.publishedAt))
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textMuted)
                        Spacer()
                        if bookmarked {
                            Image(systemName: "bookmark.fill")
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.accent)
                        }
                        importanceBadge(item.article.importance)
                    }
                    // 标题（中文优先；已读 = 标题降色 + 前置 2pt 色条，
                    // 不再整卡降透明度，收藏图标与标签保持全强度）
                    HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.sm) {
                        if read {
                            Capsule(style: .continuous)
                                .fill(AppTheme.Colors.textMuted)
                                .frame(width: 2, height: 15)
                                .alignmentGuide(.firstTextBaseline) { d in d[.bottom] - 2 }
                        }
                        Text(item.article.displayTitle)
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundStyle(read ? AppTheme.Colors.textSecondary : AppTheme.Colors.textPrimary)
                            .multilineTextAlignment(.leading)
                            .lineLimit(2)
                        if read {
                            Text("已读")
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.textMuted)
                        }
                    }
                    // 摘要
                    if let snippet = snippet(of: item.article) {
                        Text(snippet)
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                    }
                    // 学习元数据标签行
                    HStack(spacing: AppTheme.Spacing.sm) {
                        if let topicLabel = LearningMeta.topicLabel(item.topic) {
                            metaChip(topicLabel, color: AppTheme.Colors.accent)
                        }
                        if let difficulty = LearningMeta.difficultyLabel(item.article.difficultyDefault) {
                            metaChip(
                                difficulty,
                                color: item.article.difficultyDefault == LearningDifficulty.beginner.rawValue
                                    ? AppTheme.Colors.success
                                    : AppTheme.Colors.warning
                            )
                        }
                        if let contentType = LearningMeta.contentTypeLabel(item.contentType) {
                            metaChip(contentType, color: AppTheme.Colors.textMuted)
                        }
                        Spacer()
                    }
                }
            }
        }
        .buttonStyle(.plain)
        .simultaneousGesture(TapGesture().onEnded {
            Haptics.selection()
            Task { await viewModel.markRead(item) }
        })
        #if os(iOS)
        .swipeActions(edge: .trailing, allowsFullSwipe: true) {
            Button {
                Task { await viewModel.toggleBookmark(item) }
            } label: {
                Label(
                    bookmarked ? "取消收藏" : "收藏",
                    systemImage: bookmarked ? "bookmark.slash" : "bookmark"
                )
            }
            .tint(AppTheme.Colors.accent)
        }
        #endif
        #if os(macOS)
        .contextMenu {
            Button {
                Task { await viewModel.toggleBookmark(item) }
            } label: {
                Label(
                    bookmarked ? "取消收藏" : "收藏",
                    systemImage: bookmarked ? "bookmark.slash" : "bookmark"
                )
            }
        }
        #endif
    }

    /// 重要性数字徽章（★ + 数字，与 NewsView 全页统一；替代 8pt 小星星）
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

    private func metaChip(_ text: String, color: Color) -> some View {
        Text(text)
            .font(AppTheme.Typography.caption)
            .foregroundStyle(color)
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, AppTheme.Spacing.xxs)
            .background(Capsule(style: .continuous).fill(color.opacity(0.10)))
    }

    private func snippet(of article: NewsArticle) -> String? {
        let raw = article.summaryZh ?? article.body ?? article.summary
        guard let raw else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    // MARK: - 骨架屏

    private var skeletonList: some View {
        List {
            ForEach(0..<4, id: \.self) { _ in
                ADCard(padding: AppTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        SkeletonBlock(height: 10).frame(width: 160)
                        SkeletonBlock(height: 16)
                        SkeletonBlock(height: 12).frame(maxWidth: 280)
                    }
                }
                .listRowSeparator(.hidden)
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets(
                    top: AppTheme.Spacing.xs,
                    leading: AppTheme.Spacing.lg,
                    bottom: AppTheme.Spacing.xs,
                    trailing: AppTheme.Spacing.lg
                ))
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .scrollDisabled(true)
    }
}

#Preview {
    NavigationStack {
        LearningView()
    }
}
