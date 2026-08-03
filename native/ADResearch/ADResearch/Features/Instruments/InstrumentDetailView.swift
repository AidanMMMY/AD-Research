import Charts
import SwiftUI

/// 标的详情：基本信息卡 + sparkline 折线（Swift Charts 渐变面积）+ 区间切换。
///
/// 路由：AppRoute.instrumentDetail(code)。
/// 契约：GET /etfs/{code} + GET /etfs/{code}/sparkline?days=。
struct InstrumentDetailView: View {
    let code: String
    @State private var viewModel: InstrumentDetailViewModel

    init(code: String) {
        self.code = code
        _viewModel = State(initialValue: InstrumentDetailViewModel(code: code))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                headerCard
                rangePicker
                chartArea
                infoCard
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.md)
        }
        .background(AppTheme.Colors.background)
        .navigationTitle(viewModel.info?.displayName ?? code)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .refreshable {
            await viewModel.reload()
        }
        .task {
            await viewModel.loadIfNeeded()
        }
    }

    // MARK: - 头部卡（名称 + 最新价 + 区间涨跌）

    @ViewBuilder
    private var headerCard: some View {
        switch viewModel.infoState {
        case .idle, .loading:
            ADCard {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    SkeletonBlock(height: 22).frame(maxWidth: 240)
                    SkeletonBlock(height: 14).frame(width: 160)
                }
            }
        case .failed(let message):
            ADCard {
                LoadErrorView(message: message) {
                    Task { await viewModel.reload() }
                }
            }
        case .loaded:
            if let info = viewModel.info {
                ADCard {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(info.displayName)
                                .font(AppTheme.Typography.pageTitle)
                                .foregroundStyle(AppTheme.Colors.textPrimary)
                            Spacer()
                            if let latest = viewModel.points.last {
                                VStack(alignment: .trailing, spacing: AppTheme.Spacing.xxs) {
                                    Text(priceText(latest))
                                        .font(AppTheme.Typography.numericBody.weight(.semibold))
                                        .foregroundStyle(AppTheme.Colors.textPrimary)
                                    if let change = periodChange {
                                        ChangeText(value: change, font: AppTheme.Typography.numericCallout)
                                    }
                                }
                            }
                        }
                        HStack(spacing: AppTheme.Spacing.sm) {
                            Text(info.code)
                                .font(AppTheme.Typography.numericCallout)
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                            Text("·")
                                .foregroundStyle(AppTheme.Colors.textMuted)
                            Text(info.marketLabel)
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.textMuted)
                            if let type = info.instrumentType, !type.isEmpty {
                                Text("·")
                                    .foregroundStyle(AppTheme.Colors.textMuted)
                                Text(type)
                                    .font(AppTheme.Typography.caption)
                                    .foregroundStyle(AppTheme.Colors.textMuted)
                            }
                        }
                    }
                }
            }
        }
    }

    /// 区间涨跌幅（首末点）
    private var periodChange: Double? {
        guard let first = viewModel.points.first,
              let last = viewModel.points.last,
              first > 0 else { return nil }
        return (last - first) / first * 100
    }

    private func priceText(_ value: Double) -> String {
        let currency = viewModel.info?.currency ?? ""
        let formatted = NumberFormatting.tileValue(value)
        return currency.isEmpty ? formatted : "\(formatted) \(currency)"
    }

    // MARK: - 区间切换

    private var rangePicker: some View {
        Picker("区间", selection: $viewModel.range) {
            ForEach(InstrumentDetailViewModel.RangeOption.allCases) { option in
                Text(option.label).tag(option)
            }
        }
        .pickerStyle(.segmented)
    }

    // MARK: - 走势图

    @ViewBuilder
    private var chartArea: some View {
        switch viewModel.chartState {
        case .idle, .loading:
            SkeletonBlock(height: 260, cornerRadius: AppTheme.Radius.card)
        case .failed(let message):
            LoadErrorView(message: message) {
                Task { await viewModel.reload() }
            }
        case .loaded:
            if viewModel.points.count >= 2 {
                chart
            } else {
                EmptyStateView(
                    systemImage: "chart.line.flattrend.xyaxis",
                    title: "该区间没有行情数据",
                    description: "换个区间试试"
                )
            }
        }
    }

    private var chart: some View {
        let values = viewModel.points
        let dates = viewModel.dates
        let minValue = values.min() ?? 0
        let maxValue = values.max() ?? 1
        let padding = max((maxValue - minValue) * 0.08, .ulpOfOne)
        let rising = (values.last ?? 0) >= (values.first ?? 0)
        let lineColor = rising ? AppTheme.Colors.rise : AppTheme.Colors.fall
        // dates 与 points 等长（后端契约），下标对齐取日期文本
        let entries = Array(zip(values.indices, values))

        return Chart(entries, id: \.0) { index, value in
            LineMark(
                x: .value("日期", index),
                y: .value("收盘", value)
            )
            .foregroundStyle(lineColor)
            .interpolationMethod(.catmullRom)

            AreaMark(
                x: .value("日期", index),
                yStart: .value("底", minValue - padding),
                yEnd: .value("收盘", value)
            )
            .foregroundStyle(
                .linearGradient(
                    colors: [lineColor.opacity(0.24), lineColor.opacity(0.02)],
                    startPoint: .top,
                    endPoint: .bottom
                )
            )
            .interpolationMethod(.catmullRom)
        }
        .chartYScale(domain: (minValue - padding)...(maxValue + padding))
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 5)) { _ in
                AxisGridLine().foregroundStyle(AppTheme.Colors.border.opacity(0.6))
                AxisValueLabel()
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 5)) { value in
                if let index = value.as(Int.self), dates.indices.contains(index) {
                    AxisValueLabel(shortDate(dates[index]))
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
            }
        }
        .frame(height: 260)
        .animation(AppTheme.Motion.content, value: values.count)
        .accessibilityLabel("收盘价走势图")
    }

    /// ``YYYY-MM-DD`` → ``M/d``
    private func shortDate(_ string: String) -> String {
        let parts = string.split(separator: "-")
        guard parts.count == 3,
              let month = Int(parts[1]),
              let day = Int(parts[2]) else { return string }
        return "\(month)/\(day)"
    }

    // MARK: - 基本信息卡

    @ViewBuilder
    private var infoCard: some View {
        if let info = viewModel.info {
            ADCard {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    ADCardHeader(title: "基本信息", systemImage: "info.circle")
                    infoGrid(info)
                }
            }
        }
    }

    private func infoGrid(_ info: InstrumentInfo) -> some View {
        let rows: [(String, String?)] = [
            ("类别", info.category),
            ("子类别", info.subCategory),
            ("跟踪指数", info.underlyingIndex),
            ("基金公司", info.manager),
            ("基金经理", info.fundManager),
            ("基金规模", info.fundSize.map { NumberFormatting.signedMoney($0) }),
            // 契约：expense_ratio 本身已是百分数（web 直接 toFixed(2)+"%"）
            ("管理费率", info.expenseRatio.map { String(format: "%.2f%%", $0) }),
            ("行业", info.industry ?? info.sector),
            ("国家/地区", info.country),
            ("上市地", info.listingMarket),
            ("板块", info.board),
            ("成立日期", info.inceptionDate.map { DateFormatting.formatDate($0) }),
        ]
        let visible = rows.compactMap { label, value -> (String, String)? in
            guard let value, !value.isEmpty else { return nil }
            return (label, value)
        }
        return LazyVGrid(
            columns: [GridItem(.flexible(), alignment: .leading), GridItem(.flexible(), alignment: .leading)],
            spacing: AppTheme.Spacing.md
        ) {
            ForEach(visible, id: \.0) { label, value in
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                    Text(label)
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                    Text(value)
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineLimit(2)
                }
            }
        }
    }
}

#Preview {
    NavigationStack {
        InstrumentDetailView(code: "510300.SH")
    }
}
