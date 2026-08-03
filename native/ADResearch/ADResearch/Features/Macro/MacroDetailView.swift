import Charts
import SwiftUI

/// 宏观指标详情：历史序列折线图（Swift Charts 渐变面积）+ 区间切换。
///
/// 路由：AppRoute.macroDetail(code)。契约 GET /macro/indicators/{code}。
struct MacroDetailView: View {
    enum RangeOption: String, CaseIterable, Identifiable {
        case m1 = "1月"
        case m3 = "3月"
        case m6 = "6月"
        case y1 = "1年"
        case all = "全部"

        var id: String { rawValue }

        /// 对应起始日期（YYYY-MM-DD）；nil = 全部
        var startDate: String? {
            let calendar = Calendar.current
            let now = Date()
            let start: Date? = switch self {
            case .m1: calendar.date(byAdding: .month, value: -1, to: now)
            case .m3: calendar.date(byAdding: .month, value: -3, to: now)
            case .m6: calendar.date(byAdding: .month, value: -6, to: now)
            case .y1: calendar.date(byAdding: .year, value: -1, to: now)
            case .all: nil
            }
            guard let start else { return nil }
            let parts = calendar.dateComponents([.year, .month, .day], from: start)
            return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
        }
    }

    let code: String
    @State private var series: MacroIndicatorSeries?
    @State private var range: RangeOption = .m6
    @State private var loading = true
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                header
                rangePicker
                chartArea
                statsRow
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.md)
        }
        .background(AppTheme.Colors.background)
        .navigationTitle(series?.nameZh ?? code)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task(id: range) {
            await load()
        }
    }

    // MARK: - 数据

    private func load() async {
        loading = true
        error = nil
        do {
            series = try await APIClient.shared.send(
                .macroIndicatorSeries(code: code, startDate: range.startDate)
            )
        } catch let err {
            error = DigestViewModel.describe(err)
        }
        loading = false
    }

    // MARK: - 头部

    @ViewBuilder
    private var header: some View {
        if let series {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                HStack(alignment: .firstTextBaseline) {
                    Text(series.nameZh)
                        .font(AppTheme.Typography.pageTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Spacer()
                    if let latest = series.points.last {
                        VStack(alignment: .trailing, spacing: AppTheme.Spacing.xxs) {
                            Text(NumberFormatting.tileValue(latest.value, unit: series.unit))
                                .font(AppTheme.Typography.numericBody.weight(.semibold))
                                .foregroundStyle(AppTheme.Colors.textPrimary)
                            Text(latest.period)
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.textMuted)
                        }
                    }
                }
                Text("\(series.code) · \(series.source)\(series.unit.isEmpty ? "" : " · 单位：\(series.unit)")")
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
        }
    }

    private var rangePicker: some View {
        Picker("区间", selection: $range) {
            ForEach(RangeOption.allCases) { option in
                Text(option.rawValue).tag(option)
            }
        }
        .pickerStyle(.segmented)
    }

    // MARK: - 图表

    @ViewBuilder
    private var chartArea: some View {
        if loading {
            SkeletonBlock(height: 260, cornerRadius: AppTheme.Radius.card)
        } else if let error {
            LoadErrorView(message: error) {
                Task { await load() }
            }
        } else if let series, !series.points.isEmpty {
            chart(series.points, unit: series.unit)
        } else {
            EmptyStateView(
                systemImage: "chart.line.flattrend.xyaxis",
                title: "该区间没有数据",
                description: "换个区间试试"
            )
        }
    }

    private func chart(_ points: [MacroSeriesPoint], unit: String) -> some View {
        let values = points.map(\.value)
        let minValue = values.min() ?? 0
        let maxValue = values.max() ?? 1
        let padding = max((maxValue - minValue) * 0.08, .ulpOfOne)

        return Chart(points) { point in
            LineMark(
                x: .value("日期", point.period),
                y: .value("值", point.value)
            )
            .foregroundStyle(AppTheme.Colors.accent)
            .interpolationMethod(.catmullRom)

            AreaMark(
                x: .value("日期", point.period),
                yStart: .value("底", minValue - padding),
                yEnd: .value("值", point.value)
            )
            .foregroundStyle(
                .linearGradient(
                    colors: [AppTheme.Colors.accent.opacity(0.24), AppTheme.Colors.accent.opacity(0.02)],
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
            AxisMarks(values: .automatic(desiredCount: 5)) { _ in
                AxisValueLabel()
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
        }
        .frame(height: 260)
        .animation(AppTheme.Motion.content, value: points.count)
        .accessibilityLabel("历史序列图，单位 \(unit)")
    }

    // MARK: - 统计行

    @ViewBuilder
    private var statsRow: some View {
        if let series, !series.points.isEmpty {
            let values = series.points.map(\.value)
            HStack(spacing: AppTheme.Spacing.md) {
                statCell("最新", NumberFormatting.tileValue(values.last, unit: series.unit))
                statCell("区间最高", NumberFormatting.tileValue(values.max(), unit: series.unit))
                statCell("区间最低", NumberFormatting.tileValue(values.min(), unit: series.unit))
                statCell("数据点", NumberFormatting.count(values.count))
            }
        }
    }

    private func statCell(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
            Text(label)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
            Text(value)
                .font(AppTheme.Typography.numericCallout)
                .foregroundStyle(AppTheme.Colors.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(AppTheme.Spacing.sm)
        .background(
            RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                .fill(AppTheme.Colors.surface)
        )
    }
}
