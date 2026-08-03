import Charts
import SwiftUI

/// 情绪面板：全市场情绪总览 + 按标的聚合列表。
///
/// 契约：GET /research/sentiment-data/aggregate。
/// 标签语义复用 NewsShared（偏多红 / 偏空绿 / 中性灰）。
struct SentimentView: View {
    @State private var viewModel = SentimentViewModel()

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                filterBar
                content
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.md)
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("情绪")
        .refreshable {
            await viewModel.reload()
        }
        .task {
            await viewModel.loadIfNeeded()
        }
        #if os(macOS)
        .onReceive(NotificationCenter.default.publisher(for: .adRefreshRequested)) { _ in
            Task { await viewModel.reload() }
        }
        #endif
    }

    // MARK: - 筛选条

    private var filterBar: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            marketMenu
            daysMenu
            Spacer()
        }
    }

    private var marketMenu: some View {
        Menu {
            ForEach(SentimentViewModel.MarketFilter.allCases) { option in
                Button(option.label) { viewModel.market = option }
            }
        } label: {
            filterChip(viewModel.market.label)
        }
    }

    private var daysMenu: some View {
        Menu {
            ForEach(SentimentViewModel.DaysOption.allCases) { option in
                Button(option.label) { viewModel.days = option }
            }
        } label: {
            filterChip("近 \(viewModel.days.label)")
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

    // MARK: - 内容

    @ViewBuilder
    private var content: some View {
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
                    systemImage: "waveform.path.ecg",
                    title: "暂无情绪数据",
                    description: "等待新闻情绪标注完成后刷新"
                )
            } else {
                overviewCard
                ForEach(viewModel.rankedItems) { item in
                    sentimentCell(item)
                }
            }
        }
    }

    // MARK: - 总览卡

    private var overviewCard: some View {
        let stats = viewModel.overview
        return ADCard {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                ADCardHeader(
                    title: "情绪总览",
                    subtitle: "\(viewModel.market.label)市场 · 近 \(viewModel.days.rawValue) 天 · \(viewModel.items.count) 只标的",
                    systemImage: "waveform.path.ecg"
                )
                HStack(spacing: AppTheme.Spacing.md) {
                    overviewCell("偏多", stats.positive, color: AppTheme.Colors.rise)
                    overviewCell("中性", stats.neutral, color: AppTheme.Colors.textMuted)
                    overviewCell("偏空", stats.negative, color: AppTheme.Colors.fall)
                }
            }
        }
    }

    private func overviewCell(_ label: String, _ count: Int, color: Color) -> some View {
        VStack(spacing: AppTheme.Spacing.xxs) {
            Text(NumberFormatting.count(count))
                .font(AppTheme.Typography.numericBody.weight(.semibold))
                .foregroundStyle(color)
            Text(label)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(
            RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                .fill(AppTheme.Colors.surface)
        )
    }

    // MARK: - 标的情绪卡

    private func sentimentCell(_ item: SentimentAggregateItem) -> some View {
        ADCard(padding: AppTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                        Text(item.displayName)
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .lineLimit(1)
                        Text(item.instrumentCode)
                            .font(AppTheme.Typography.numericCallout)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                    }
                    Spacer(minLength: AppTheme.Spacing.sm)
                    NewsSentimentChip(label: item.label)
                    Text(scoreText(item.avgScore))
                        .font(AppTheme.Typography.numericCallout.weight(.medium))
                        .foregroundStyle(NewsLabels.sentimentColor(item.label))
                }

                HStack(spacing: AppTheme.Spacing.md) {
                    breakdownRow(item)
                    Spacer()
                    if item.sparkline.count >= 2 {
                        sparkline(item)
                    }
                }

                if let latest = item.latestTitle, !latest.isEmpty {
                    Text("最新：\(latest)")
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                        .lineLimit(1)
                }
            }
        }
    }

    /// 情绪分 [-1, 1]，带符号两位小数
    private func scoreText(_ score: Double) -> String {
        String(format: "%@%.2f", score >= 0 ? "+" : "", score)
    }

    private func breakdownRow(_ item: SentimentAggregateItem) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Text("多 \(item.bull)")
                .foregroundStyle(AppTheme.Colors.rise)
            Text("空 \(item.bear)")
                .foregroundStyle(AppTheme.Colors.fall)
            Text("中 \(item.neutral)")
                .foregroundStyle(AppTheme.Colors.textMuted)
            Text("· \(item.count) 篇")
                .foregroundStyle(AppTheme.Colors.textMuted)
        }
        .font(AppTheme.Typography.caption)
    }

    /// 14 日情绪分迷你走势
    private func sparkline(_ item: SentimentAggregateItem) -> some View {
        let color = NewsLabels.sentimentColor(item.label)
        return Chart(Array(item.sparkline.enumerated()), id: \.offset) { index, value in
            LineMark(
                x: .value("日", index),
                y: .value("分", value)
            )
            .foregroundStyle(color)
            .interpolationMethod(.catmullRom)

            AreaMark(
                x: .value("日", index),
                yStart: .value("零", 0),
                yEnd: .value("分", value)
            )
            .foregroundStyle(
                .linearGradient(
                    colors: [color.opacity(0.20), color.opacity(0.02)],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .interpolationMethod(.catmullRom)
        }
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .frame(width: 96, height: 32)
        .accessibilityLabel("14 日情绪走势")
    }

    private var skeleton: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            ADCard {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    SkeletonBlock(height: 16).frame(width: 140)
                    SkeletonBlock(height: 44)
                }
            }
            ForEach(0..<4, id: \.self) { _ in
                ADCard(padding: AppTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        SkeletonBlock(height: 16).frame(maxWidth: 200)
                        SkeletonBlock(height: 12).frame(maxWidth: 280)
                    }
                }
            }
        }
    }
}

#Preview {
    NavigationStack {
        SentimentView()
    }
}
