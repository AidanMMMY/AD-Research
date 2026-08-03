import SwiftUI

/// 首页（Dashboard）：全球资产脉搏 + 每日研报摘要卡 + 平台概览（真数据）+ 自选异动横条。
///
/// 布局：iOS 卡片堆叠（refreshable 下拉刷新）；
/// macOS 三栏——脉搏 3fr / 研报 2fr / 平台概览固定宽（stats/overview 真数据，
/// 取代原「将在后续迭代接入」占位卡）。
/// 数据见 ``DashboardViewModel``（契约对齐 web Dashboard）。
struct DashboardView: View {
    @Environment(AppState.self) private var appState
    @State private var viewModel = DashboardViewModel()

    var body: some View {
        ScrollView {
            #if os(iOS)
            iosLayout
            #else
            macLayout
            #endif
        }
        .background(AppTheme.Colors.background)
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

    // MARK: - iOS：单列卡片堆叠

    #if os(iOS)
    private var iosLayout: some View {
        LazyVStack(spacing: AppTheme.Spacing.lg) {
            statusHeader
            moversStrip
            pulseCard
            digestCard
        }
        .padding(.horizontal, AppTheme.Spacing.lg)
        .padding(.vertical, AppTheme.Spacing.md)
    }
    #endif

    // MARK: - macOS：三栏（脉搏 3fr + 研报 2fr + 平台概览固定宽）

    #if os(macOS)
    private var macLayout: some View {
        // 脉搏 3fr : 研报 2fr（剩余宽度六四开），平台概览固定 260pt
        let spacing = AppTheme.Spacing.lg
        let statsWidth: CGFloat = 260
        return VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            statusHeader
            moversStrip
            HStack(alignment: .top, spacing: spacing) {
                pulseCard
                    .containerRelativeFrame(.horizontal, alignment: .topLeading) { width, _ in
                        max((width - statsWidth - spacing * 2) * 0.6, 0)
                    }
                digestCard
                    .containerRelativeFrame(.horizontal, alignment: .topLeading) { width, _ in
                        max((width - statsWidth - spacing * 2) * 0.4, 0)
                    }
                statsOverviewCard
                    .frame(width: statsWidth, alignment: .topLeading)
            }
        }
        .padding(AppTheme.Spacing.xl)
    }
    #endif

    // MARK: - 顶部状态条（真实数据状态圆点 + 上次更新时间）

    private var statusHeader: some View {
        // 30s 周期刷新，让「x 分钟前」随时间推进
        TimelineView(.periodic(from: .now, by: 30)) { context in
            HStack(spacing: AppTheme.Spacing.sm) {
                Circle()
                    .fill(statusColor)
                    .frame(width: 8, height: 8)
                Text(DateFormatting.nowWithWeekday())
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                Text("·")
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                Text(lastUpdatedText(at: context.date))
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                if viewModel.staleCount > 0 {
                    Text("· \(viewModel.staleCount) 项数据陈旧")
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.warning)
                }
                Spacer()
            }
        }
    }

    /// 加载中灰 / 失败红 / 陈旧黄 / 正常绿
    private var statusColor: Color {
        switch viewModel.dataStatus {
        case .loading: return AppTheme.Colors.textMuted
        case .ok: return AppTheme.Colors.success
        case .stale: return AppTheme.Colors.warning
        case .failed: return AppTheme.Colors.error
        }
    }

    private func lastUpdatedText(at now: Date) -> String {
        guard let last = viewModel.lastUpdated else { return "数据加载中" }
        let interval = max(now.timeIntervalSince(last), 0)
        if interval < 60 { return "上次更新 刚刚" }
        if interval < 3600 { return "上次更新 \(Int(interval / 60)) 分钟前" }
        return "上次更新 \(Int(interval / 3600)) 小时前"
    }

    // MARK: - 全球资产脉搏

    private var pulseCard: some View {
        ADCard {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                ADCardHeader(
                    title: "全球资产脉搏",
                    subtitle: "宏观快照 + 实时覆盖",
                    systemImage: "globe"
                ) {
                    Button {
                        Haptics.selection()
                        appState.navigate(to: .macro, route: .section(.macro))
                    } label: {
                        Text("查看全部")
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.accent)
                    }
                    .buttonStyle(.plain)
                }

                if viewModel.isLoadingPulse && viewModel.pulseGroups.isEmpty {
                    pulseSkeleton
                } else if let error = viewModel.pulseError, viewModel.pulseGroups.isEmpty {
                    LoadErrorView(message: error) {
                        Task { await viewModel.load() }
                    }
                } else {
                    pulseContent
                }
            }
        }
    }

    private var pulseContent: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            ForEach(viewModel.pulseGroups) { group in
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    Text(group.label)
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: 96), spacing: AppTheme.Spacing.sm)],
                        spacing: AppTheme.Spacing.sm
                    ) {
                        ForEach(group.tiles) { tile in
                            pulseTile(tile)
                        }
                    }
                }
            }
        }
        .animation(AppTheme.Motion.content, value: viewModel.pulseGroups)
    }

    private func pulseTile(_ tile: DashboardViewModel.PulseTile) -> some View {
        Button {
            Haptics.selection()
            appState.navigate(to: .macro, route: .macroDetail(tile.code))
        } label: {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text(tile.title)
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                    .lineLimit(1)
                Text(NumberFormatting.tileValue(tile.value, unit: tile.unit))
                    .font(AppTheme.Typography.numericCallout)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                ChangeText(value: tile.changePct, font: AppTheme.Typography.caption.monospacedDigit())
            }
            .padding(AppTheme.Spacing.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                    .fill(AppTheme.Colors.surface)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// 骨架屏（redacted 体系外的显式骨架，避免裸 spinner）
    private var pulseSkeleton: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            ForEach(0..<3, id: \.self) { _ in
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    SkeletonBlock(height: 10)
                        .frame(width: 64)
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: 96), spacing: AppTheme.Spacing.sm)],
                        spacing: AppTheme.Spacing.sm
                    ) {
                        ForEach(0..<4, id: \.self) { _ in
                            SkeletonBlock(height: 64, cornerRadius: AppTheme.Radius.control)
                        }
                    }
                }
            }
        }
    }

    // MARK: - 每日研报摘要卡（对齐 web DigestSummaryCard）

    private var digestCard: some View {
        ADCard {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                ADCardHeader(
                    title: "每日研报",
                    subtitle: viewModel.digestSummary.map { "\($0.reportDate) · AI 夜间综合研报" } ?? "AI 夜间综合研报",
                    systemImage: "doc.text.magnifyingglass"
                ) {
                    if viewModel.digestSummary != nil {
                        Button {
                            Haptics.selection()
                            appState.navigate(to: .digest, route: .section(.digest))
                        } label: {
                            Text("阅读全文")
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.accent)
                        }
                        .buttonStyle(.plain)
                    }
                }

                switch viewModel.digestState {
                case .idle, .loading:
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        SkeletonBlock(height: 16)
                        SkeletonBlock(height: 12)
                        SkeletonBlock(height: 12).frame(maxWidth: 220)
                    }
                case .empty:
                    Text("今日研报生成中，每日 6:30 发布")
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                case .failed(let message):
                    LoadErrorView(message: message) {
                        Task { await viewModel.load() }
                    }
                case .loaded:
                    if let summary = viewModel.digestSummary {
                        digestBody(summary)
                    }
                }
            }
        }
    }

    private func digestBody(_ summary: DigestLatestSummary) -> some View {
        Button {
            Haptics.selection()
            appState.navigate(to: .digest, route: .digestDetail(summary.reportDate))
        } label: {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Text(summary.title)
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .multilineTextAlignment(.leading)
                Text(MarkdownRenderer.plainText(fromMarkdown: summary.summaryMd).isEmpty
                     ? "点击查看今日研报全文"
                     : MarkdownRenderer.plainText(fromMarkdown: summary.summaryMd))
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }

    // MARK: - 自选异动横条（favorites × snapshot，|涨跌幅| 前 5；无自选隐藏）

    @ViewBuilder
    private var moversStrip: some View {
        if viewModel.isLoadingMovers && viewModel.favoriteMovers.isEmpty {
            ADCard(padding: AppTheme.Spacing.md) {
                HStack(spacing: AppTheme.Spacing.sm) {
                    SkeletonBlock(height: 12).frame(width: 64)
                    SkeletonBlock(height: 12)
                }
            }
        } else if !viewModel.favoriteMovers.isEmpty {
            ADCard(padding: AppTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    ADCardHeader(title: "自选异动", systemImage: "bolt.horizontal") {
                        Button {
                            Haptics.selection()
                            appState.navigate(to: .portfolio, route: .section(.portfolio))
                        } label: {
                            Text("我的自选")
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.accent)
                        }
                        .buttonStyle(.plain)
                    }
                    #if os(iOS)
                    // iOS 屏宽窄：横向滑动条，单块固定宽保证可读
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: AppTheme.Spacing.sm) {
                            ForEach(viewModel.favoriteMovers) { mover in
                                moverCell(mover)
                                    .frame(width: 156)
                            }
                        }
                    }
                    #else
                    HStack(spacing: AppTheme.Spacing.sm) {
                        ForEach(viewModel.favoriteMovers) { mover in
                            moverCell(mover)
                        }
                    }
                    #endif
                }
            }
        }
    }

    /// 紧凑异动块：涨跌色块 + 名称 + 现价 + 涨跌幅，点击进标的详情
    private func moverCell(_ mover: DashboardViewModel.FavoriteMover) -> some View {
        Button {
            Haptics.selection()
            appState.navigate(to: .instruments, route: .instrumentDetail(mover.code))
        } label: {
            HStack(spacing: AppTheme.Spacing.sm) {
                RoundedRectangle(cornerRadius: 2, style: .continuous)
                    .fill(AppTheme.Colors.changeColor(mover.changePct))
                    .frame(width: 4, height: 32)
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                    Text(mover.name)
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineLimit(1)
                    HStack(spacing: AppTheme.Spacing.xs) {
                        Text(NumberFormatting.tileValue(mover.close))
                            .font(AppTheme.Typography.caption.monospacedDigit())
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                        ChangeText(value: mover.changePct, font: AppTheme.Typography.caption.monospacedDigit())
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(AppTheme.Spacing.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                    .fill(AppTheme.Colors.surface)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: - macOS 平台概览卡（GET /stats/overview 真数据）

    #if os(macOS)
    private var statsOverviewCard: some View {
        ADCard {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                ADCardHeader(title: "平台概览", subtitle: "数据覆盖情况", systemImage: "chart.bar.doc.horizontal")
                if viewModel.isLoadingOverview && viewModel.overview == nil {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        ForEach(0..<4, id: \.self) { _ in
                            SkeletonBlock(height: 12)
                        }
                    }
                } else if let overview = viewModel.overview {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        statRow("标的总数", value: NumberFormatting.count(overview.etfCount))
                        statRow("评分记录", value: NumberFormatting.count(overview.scoreCount))
                        statRow("指标记录", value: NumberFormatting.count(overview.indicatorCount))
                        statRow("分类 / 市场", value: "\(overview.categoryCount) / \(overview.marketCount)")
                        statRow("评分模板", value: NumberFormatting.count(overview.templateCount))
                        Divider().overlay(AppTheme.Colors.border)
                        statRow("指标最新", value: overview.latestIndicatorDate ?? "—")
                        statRow("评分最新", value: overview.latestScoreDate ?? "—")
                    }
                } else {
                    Text("统计数据暂不可用")
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
            }
        }
    }

    private func statRow(_ label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
            Spacer()
            Text(value)
                .font(AppTheme.Typography.numericCallout)
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .lineLimit(1)
        }
    }
    #endif
}

#Preview {
    DashboardView()
        .environment(AppState())
}
