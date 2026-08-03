import SwiftUI

/// 每日研报（Digest）：顶部今日卡 + 历史列表。
///
/// iOS：单列卡片流，refreshable；macOS：今日卡置顶 + 自适应历史网格。
/// 点击进入 ``DigestDetailView``（路由 AppRoute.digestDetail(date)）。
struct DigestView: View {
    @Environment(AppState.self) private var appState
    @State private var viewModel = DigestViewModel()

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                todayCard
                historySection
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.md)
            #if os(macOS)
            .padding(.horizontal, AppTheme.Spacing.md)
            #endif
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("每日研报")
        .refreshable {
            await viewModel.load()
        }
        .task {
            await viewModel.loadIfNeeded()
        }
        #if os(macOS)
        .onReceive(NotificationCenter.default.publisher(for: .adRefreshRequested)) { _ in
            Task { await viewModel.load() }
        }
        #endif
    }

    // MARK: - 今日研报卡

    @ViewBuilder
    private var todayCard: some View {
        if let summary = viewModel.todaySummary {
            Button {
                Haptics.selection()
                appState.navigate(to: .digest, route: .digestDetail(summary.reportDate))
            } label: {
                ADCard {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                        ADCardHeader(
                            title: summary.title,
                            subtitle: "\(summary.reportDate) · \(NumberFormatting.count(summary.contentChars)) 字",
                            systemImage: "sparkles.rectangle.stack"
                        ) {
                            statusBadge(summary.status)
                        }
                        if let excerpt = excerpt(of: summary.summaryMd) {
                            Text(excerpt)
                                .font(AppTheme.Typography.callout)
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                                .lineLimit(3)
                                .multilineTextAlignment(.leading)
                        }
                        HStack(spacing: AppTheme.Spacing.xs) {
                            Text("阅读全文")
                                .font(AppTheme.Typography.caption)
                            Image(systemName: "chevron.right")
                                .font(.caption2)
                        }
                        .foregroundStyle(AppTheme.Colors.accent)
                    }
                }
            }
            .buttonStyle(.plain)
            .transition(.opacity.combined(with: .move(edge: .top)))
        } else if viewModel.todayLoaded {
            ADCard {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    ADCardHeader(
                        title: "今日研报生成中",
                        subtitle: "每日 06:30（北京时间）自动发布",
                        systemImage: "clock"
                    )
                    Text("今晨的综合研报尚未出报，可先从下方历史列表阅读往期。")
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
            }
        } else {
            ADCard {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    SkeletonBlock(height: 18).frame(maxWidth: 260)
                    SkeletonBlock(height: 12)
                    SkeletonBlock(height: 12).frame(maxWidth: 200)
                }
            }
        }
    }

    // MARK: - 历史列表

    @ViewBuilder
    private var historySection: some View {
        switch viewModel.state {
        case .idle, .loading:
            historySkeleton
        case .failed(let message):
            LoadErrorView(message: message) {
                Task { await viewModel.load() }
            }
        case .loaded:
            if viewModel.items.isEmpty {
                EmptyStateView(
                    systemImage: "doc.text.magnifyingglass",
                    title: "还没有研报",
                    description: "首份每日研报将于明晨 06:30 发布"
                )
            } else {
                historyList
            }
        }
    }

    private var historyList: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Text("历史研报")
                .font(AppTheme.Typography.cardTitle)
                .foregroundStyle(AppTheme.Colors.textPrimary)
            ForEach(viewModel.items) { item in
                historyCell(item)
            }
            if viewModel.canLoadMore {
                HStack {
                    Spacer()
                    SkeletonBlock(height: 10).frame(width: 120)
                    Spacer()
                }
            }
        }
        .animation(AppTheme.Motion.content, value: viewModel.items.count)
    }

    private func historyCell(_ item: DigestListItem) -> some View {
        Button {
            Haptics.selection()
            appState.navigate(to: .digest, route: .digestDetail(item.reportDate))
        } label: {
            ADCard(padding: AppTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(item.reportDate)
                            .font(AppTheme.Typography.caption.monospacedDigit())
                            .foregroundStyle(AppTheme.Colors.textMuted)
                        Spacer()
                        statusBadge(item.status)
                    }
                    Text(item.title)
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .multilineTextAlignment(.leading)
                        .lineLimit(2)
                    if let excerpt = excerpt(of: item.summaryMd) {
                        Text(excerpt)
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                    }
                }
            }
        }
        .buttonStyle(.plain)
        .onAppear {
            // 滚动到底部分页
            if item.id == viewModel.items.last?.id {
                Task { await viewModel.loadMore() }
            }
        }
    }

    private var historySkeleton: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            ForEach(0..<3, id: \.self) { _ in
                ADCard(padding: AppTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        SkeletonBlock(height: 10).frame(width: 100)
                        SkeletonBlock(height: 16)
                        SkeletonBlock(height: 12).frame(maxWidth: 240)
                    }
                }
            }
        }
    }

    // MARK: - 小部件

    private func statusBadge(_ status: DigestStatus) -> some View {
        let (text, color): (String, Color) = {
            switch status {
            case .success: return ("完整", AppTheme.Colors.success)
            case .partial: return ("部分降级", AppTheme.Colors.warning)
            case .running: return ("生成中", AppTheme.Colors.accent)
            case .pending: return ("排队中", AppTheme.Colors.textMuted)
            case .failed: return ("失败", AppTheme.Colors.error)
            }
        }()
        return Text(text)
            .font(AppTheme.Typography.caption)
            .foregroundStyle(color)
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, AppTheme.Spacing.xxs)
            .background(Capsule(style: .continuous).fill(color.opacity(0.12)))
    }

    private func excerpt(of markdown: String?) -> String? {
        let text = MarkdownRenderer.plainText(fromMarkdown: markdown)
        return text.isEmpty ? nil : text
    }
}

#Preview {
    NavigationStack {
        DigestView()
            .environment(AppState())
    }
}
