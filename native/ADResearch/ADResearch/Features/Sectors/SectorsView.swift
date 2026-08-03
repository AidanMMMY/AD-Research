import SwiftUI

/// 板块轮动：板块表现卡片列表（涨跌幅 + 相对强弱 + 动量排名）。
///
/// 契约：GET /sector-rotation?classification=GICS|SW。
struct SectorsView: View {
    @State private var viewModel = SectorsViewModel()

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                classificationPicker
                content
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.md)
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("板块")
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

    // MARK: - 分类切换

    @ViewBuilder
    private var classificationPicker: some View {
        #if os(macOS)
        // 桌面端 segmented 不拉满：限宽 320 右对齐
        HStack {
            Spacer()
            picker
                .frame(maxWidth: 320)
        }
        #else
        picker
        #endif
    }

    private var picker: some View {
        Picker("分类体系", selection: $viewModel.classification) {
            ForEach(SectorsViewModel.Classification.allCases) { option in
                Text(option.label).tag(option)
            }
        }
        .pickerStyle(.segmented)
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
            if viewModel.sectors.isEmpty {
                EmptyStateView(
                    systemImage: "square.grid.2x2",
                    title: "暂无板块数据",
                    description: "等待板块指标计算完成后刷新"
                )
            } else {
                marketAverageCard
                if !viewModel.signals.isEmpty {
                    signalsCard
                }
                ForEach(viewModel.rankedSectors) { sector in
                    sectorCell(sector)
                }
            }
        }
    }

    // MARK: - 市场均值卡

    @ViewBuilder
    private var marketAverageCard: some View {
        if let avg = viewModel.marketAvg {
            ADCard {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    ADCardHeader(
                        title: "市场均值",
                        subtitle: viewModel.tradeDate.map { "交易日 \(DateFormatting.formatDate($0))" },
                        systemImage: "chart.bar.xaxis"
                    )
                    HStack(spacing: AppTheme.Spacing.md) {
                        avgCell("1周", avg.return1w)
                        avgCell("1月", avg.return1m)
                        avgCell("3月", avg.return3m)
                        avgCell("1年", avg.return1y)
                    }
                }
            }
        }
    }

    /// 契约：return_* 为小数（0.05 = 5%，app/data/indicators/risk.py），
    /// web 统一 ×100 显示，这里对齐
    private func avgCell(_ label: String, _ value: Double) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
            Text(label)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
            ChangeText(value: value * 100, font: AppTheme.Typography.numericCallout)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - 轮动信号卡

    private var signalsCard: some View {
        ADCard {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                ADCardHeader(title: "轮动信号", systemImage: "arrow.left.arrow.right")
                ForEach(viewModel.signals.prefix(4)) { signal in
                    HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.sm) {
                        Image(systemName: signal.type == "up" ? "arrow.up.right" : "arrow.down.right")
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(signal.type == "up" ? AppTheme.Colors.rise : AppTheme.Colors.fall)
                            .symbolRenderingMode(.hierarchical)
                        Text(signal.message)
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .multilineTextAlignment(.leading)
                    }
                }
            }
        }
    }

    // MARK: - 板块卡片

    private func sectorCell(_ sector: SectorPerformance) -> some View {
        ADCard(padding: AppTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(alignment: .firstTextBaseline) {
                    Text(sector.sector)
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineLimit(1)
                    Text("\(sector.count) 只")
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                    Spacer()
                    rankBadge(sector.momentumRank)
                }
                HStack(spacing: AppTheme.Spacing.md) {
                    returnCell("1周", sector.return1w)
                    returnCell("1月", sector.return1m)
                    returnCell("3月", sector.return3m)
                    rsCell(sector.relativeStrength1m)
                }
                returnBar(sector.return1m)
            }
        }
    }

    /// 当期板块 1月收益绝对值最大者（板块间归一分母；极小值兜底防除零）
    private var maxAbsReturn1m: Double {
        max(viewModel.rankedSectors.map { abs($0.return1m) }.max() ?? 0, 0.000_001)
    }

    /// 1月收益横向条形：0 轴居中，正值右伸（rise）/ 负值左伸（fall），
    /// 板块间按当期最大绝对收益归一，方便横向比较强弱
    private func returnBar(_ value: Double) -> some View {
        let fraction = min(abs(value) / maxAbsReturn1m, 1)
        return GeometryReader { geo in
            let half = (geo.size.width - 1) / 2
            let barWidth = max(half * fraction, 2)
            ZStack(alignment: .leading) {
                Capsule(style: .continuous)
                    .fill(AppTheme.Colors.surface)
                // 0 轴
                Rectangle()
                    .fill(AppTheme.Colors.textMuted.opacity(0.4))
                    .frame(width: 1)
                    .offset(x: half)
                Capsule(style: .continuous)
                    .fill(value >= 0 ? AppTheme.Colors.rise : AppTheme.Colors.fall)
                    .frame(width: barWidth)
                    .offset(x: value >= 0 ? half + 1 : half + 1 - barWidth)
            }
        }
        .frame(height: 8)
        .accessibilityLabel("1月收益 \(NumberFormatting.percent(value * 100))")
    }

    private func rankBadge(_ rank: Int) -> some View {
        Text("#\(rank)")
            .font(AppTheme.Typography.numericCallout)
            .foregroundStyle(AppTheme.Colors.accent)
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, AppTheme.Spacing.xxs)
            .background(Capsule(style: .continuous).fill(AppTheme.Colors.accentSoft))
    }

    private func returnCell(_ label: String, _ value: Double) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
            Text(label)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
            ChangeText(value: value * 100, font: AppTheme.Typography.numericCallout)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// 相对强弱（1月超额收益，小数 → 百分点显示，对齐 web "+x.xx%"）
    private func rsCell(_ value: Double) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
            Text("相对强弱")
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
            ChangeText(value: value * 100, font: AppTheme.Typography.numericCallout)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var skeleton: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            ForEach(0..<6, id: \.self) { _ in
                ADCard(padding: AppTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        SkeletonBlock(height: 16).frame(maxWidth: 180)
                        SkeletonBlock(height: 12)
                    }
                }
            }
        }
    }
}

#Preview {
    NavigationStack {
        SectorsView()
    }
}
