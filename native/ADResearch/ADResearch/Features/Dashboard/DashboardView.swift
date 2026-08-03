import SwiftUI

/// 首页（Dashboard）：全球资产脉搏 + 每日研报摘要卡。
///
/// 布局：iOS 卡片堆叠（refreshable 下拉刷新）；macOS 三栏网格。
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
            pulseCard
            digestCard
        }
        .padding(.horizontal, AppTheme.Spacing.lg)
        .padding(.vertical, AppTheme.Spacing.md)
    }
    #endif

    // MARK: - macOS：三栏网格（对齐 web cc-grid 的信息层级）

    #if os(macOS)
    private var macLayout: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            statusHeader
            HStack(alignment: .top, spacing: AppTheme.Spacing.lg) {
                pulseCard
                    .frame(maxWidth: .infinity)
                digestCard
                    .frame(maxWidth: .infinity)
                sideInfoCard
                    .frame(maxWidth: .infinity)
            }
        }
        .padding(AppTheme.Spacing.xl)
    }
    #endif

    // MARK: - 顶部状态条（对齐 web cc-topbar：日期 + 连接状态）

    private var statusHeader: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Circle()
                .fill(AppTheme.Colors.success)
                .frame(width: 8, height: 8)
            Text(DateFormatting.nowWithWeekday())
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

    // MARK: - macOS 侧栏补充卡（平台信息占位，后续模块接 KPI）

    #if os(macOS)
    private var sideInfoCard: some View {
        ADCard {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                ADCardHeader(title: "平台概览", subtitle: "数据覆盖情况", systemImage: "chart.bar.doc.horizontal")
                Text("平台 KPI（标的总数 / 评分覆盖 / 分类数 / 标的池）将在后续迭代接入。")
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
            }
        }
    }
    #endif
}

#Preview {
    DashboardView()
        .environment(AppState())
}
