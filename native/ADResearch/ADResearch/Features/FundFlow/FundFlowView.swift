import SwiftUI

/// 资金流面板（A 股）：大盘主力快照 + 板块 / ETF / 资金信号 三分段。
///
/// 契约见 ``FundFlowViewModel``。涨跌色遵循 A 股惯例（红涨绿跌，Theme rise/fall）。
struct FundFlowView: View {
    @State private var viewModel = FundFlowViewModel()
    @Environment(AppState.self) private var appState

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                marketOverview
                segmentBar
                segmentContent
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.md)
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("资金流")
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

    // MARK: - 大盘快照

    private var marketOverview: some View {
        ADCard {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                ADCardHeader(
                    title: "大盘主力净流入",
                    subtitle: viewModel.tradeDate.map { "交易日 \($0)" },
                    systemImage: "arrow.left.arrow.right"
                ) { EmptyView() }

                if let market = viewModel.market {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        marketTile(
                            title: "沪深合计",
                            inflow: market.totalMainNetInflow,
                            pct: market.totalMainNetPct
                        )
                        marketTile(
                            title: "沪市",
                            inflow: market.shMainNetInflow,
                            pct: market.shMainNetPct
                        )
                        marketTile(
                            title: "深市",
                            inflow: market.szMainNetInflow,
                            pct: market.szMainNetPct
                        )
                    }
                } else {
                    Text("暂无大盘资金流数据")
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, AppTheme.Spacing.md)
                }
            }
        }
    }

    private func marketTile(title: String, inflow: Double?, pct: Double?) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
            Text(title)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
            Text(FundFlowFormat.money(inflow))
                .font(AppTheme.Typography.title3.monospacedDigit())
                .foregroundStyle(AppTheme.Colors.changeColor(inflow))
            Text(FundFlowFormat.pct(pct))
                .font(AppTheme.Typography.caption.monospacedDigit())
                .foregroundStyle(AppTheme.Colors.changeColor(pct))
        }
        .padding(AppTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: AppTheme.Radius.chip, style: .continuous)
                .fill(AppTheme.Colors.changeColor(inflow).opacity(inflow == nil ? 0 : 0.06))
        )
    }

    // MARK: - 分段条

    private var segmentBar: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Picker("分段", selection: Binding(
                get: { viewModel.segment },
                set: { viewModel.segment = $0 }
            )) {
                ForEach(FundFlowViewModel.Segment.allCases) { segment in
                    Text(segment.label).tag(segment)
                }
            }
            .pickerStyle(.segmented)
            .frame(maxWidth: 320)

            if viewModel.segment == .sector {
                Menu {
                    ForEach(FundFlowViewModel.SectorTypeFilter.allCases) { option in
                        Button(option.label) { viewModel.sectorType = option }
                    }
                } label: {
                    HStack(spacing: AppTheme.Spacing.xs) {
                        Text(viewModel.sectorType.label).font(AppTheme.Typography.caption)
                        Image(systemName: "chevron.down").font(.system(size: 9))
                    }
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, AppTheme.Spacing.xs)
                    .background(
                        Capsule().fill(AppTheme.Colors.elevated)
                    )
                    .overlay(
                        Capsule().strokeBorder(AppTheme.Colors.border, lineWidth: 0.5)
                    )
                }
                .menuStyle(.borderlessButton)
            }

            Spacer()
        }
    }

    // MARK: - 分段内容

    @ViewBuilder
    private var segmentContent: some View {
        switch viewModel.state {
        case .idle, .loading:
            ProgressView()
                .frame(maxWidth: .infinity)
                .padding(.vertical, AppTheme.Spacing.xl)
        case .failed(let message):
            ADCard {
                VStack(spacing: AppTheme.Spacing.sm) {
                    Text(message)
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                    Button("重试") { Task { await viewModel.reload() } }
                        .buttonStyle(.borderedProminent)
                }
                .frame(maxWidth: .infinity)
            }
        case .loaded:
            switch viewModel.segment {
            case .sector: sectorList
            case .etf: etfList
            case .signal: signalList
            }
        }
    }

    // MARK: 板块列表（按 |主力净流入| 排序，行内比例条）

    private var sectorList: some View {
        let items = viewModel.filteredSectors
        let maxAbs = items.map { abs($0.mainNetInflow ?? 0) }.max() ?? 1
        return ADCard(compact: true) {
            VStack(alignment: .leading, spacing: 0) {
                if items.isEmpty {
                    emptyHint("暂无板块资金流数据")
                } else {
                    ForEach(items) { item in
                        HStack(spacing: AppTheme.Spacing.sm) {
                            VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                                HStack(spacing: AppTheme.Spacing.xs) {
                                    Text(item.sectorName)
                                        .font(AppTheme.Typography.callout)
                                        .foregroundStyle(AppTheme.Colors.textPrimary)
                                    Text(item.sectorType)
                                        .font(AppTheme.Typography.caption)
                                        .foregroundStyle(AppTheme.Colors.textMuted)
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 1)
                                        .background(Capsule().fill(AppTheme.Colors.elevated))
                                }
                                if let leader = item.leadingStock, !leader.isEmpty {
                                    Text("领涨 \(leader)")
                                        .font(AppTheme.Typography.caption)
                                        .foregroundStyle(AppTheme.Colors.textMuted)
                                }
                                flowBar(value: item.mainNetInflow, maxAbs: maxAbs)
                            }
                            Spacer(minLength: AppTheme.Spacing.sm)
                            VStack(alignment: .trailing, spacing: AppTheme.Spacing.xxs) {
                                Text(FundFlowFormat.money(item.mainNetInflow))
                                    .font(AppTheme.Typography.numericCallout)
                                    .foregroundStyle(AppTheme.Colors.changeColor(item.mainNetInflow))
                                Text(FundFlowFormat.pct(item.mainNetPct))
                                    .font(AppTheme.Typography.caption.monospacedDigit())
                                    .foregroundStyle(AppTheme.Colors.textSecondary)
                            }
                        }
                        .padding(.vertical, AppTheme.Spacing.sm)
                        .adHoverRow()
                        if item.id != items.last?.id {
                            Divider().opacity(0.5)
                        }
                    }
                }
            }
        }
    }

    /// 行内净流入比例条：正红右伸 / 负绿左伸（0 轴居中）
    private func flowBar(value: Double?, maxAbs: Double) -> some View {
        let ratio = min(abs(value ?? 0) / max(maxAbs, 1), 1)
        let isPositive = (value ?? 0) >= 0
        return GeometryReader { geo in
            let half = geo.size.width / 2
            ZStack(alignment: isPositive ? .leading : .trailing) {
                Capsule().fill(AppTheme.Colors.border.opacity(0.35)).frame(height: 3)
                Capsule()
                    .fill(AppTheme.Colors.changeColor(value).opacity(0.7))
                    .frame(width: max(ratio * half, 2), height: 3)
                    .offset(x: isPositive ? half : -half)
            }
            .frame(maxWidth: .infinity)
        }
        .frame(height: 4)
    }

    // MARK: ETF 列表

    private var etfList: some View {
        let items = viewModel.sortedEtfs
        return ADCard(compact: true) {
            VStack(alignment: .leading, spacing: 0) {
                if items.isEmpty {
                    emptyHint("暂无 ETF 资金流数据")
                } else {
                    ForEach(items) { item in
                        Button {
                            appState.navigate(to: .instruments, route: .instrumentDetail(item.tsCode))
                        } label: {
                            HStack(spacing: AppTheme.Spacing.sm) {
                                VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                                    Text(item.tsCode)
                                        .font(AppTheme.Typography.numericCallout)
                                        .foregroundStyle(AppTheme.Colors.textPrimary)
                                    HStack(spacing: AppTheme.Spacing.sm) {
                                        if let premium = item.premiumRate {
                                            Text("溢价 \(FundFlowFormat.pct(premium))")
                                        }
                                        if let change = item.sharesChange {
                                            Text("份额 \(FundFlowFormat.money(change, digits: 0))")
                                        }
                                    }
                                    .font(AppTheme.Typography.caption)
                                    .foregroundStyle(AppTheme.Colors.textMuted)
                                }
                                Spacer(minLength: AppTheme.Spacing.sm)
                                VStack(alignment: .trailing, spacing: AppTheme.Spacing.xxs) {
                                    Text(FundFlowFormat.money(item.inferredNetInflow))
                                        .font(AppTheme.Typography.numericCallout)
                                        .foregroundStyle(AppTheme.Colors.changeColor(item.inferredNetInflow))
                                    Text("推算净流入")
                                        .font(AppTheme.Typography.caption)
                                        .foregroundStyle(AppTheme.Colors.textMuted)
                                }
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 10, weight: .semibold))
                                    .foregroundStyle(AppTheme.Colors.textMuted)
                            }
                            .padding(.vertical, AppTheme.Spacing.sm)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .adHoverRow()
                        if item.id != items.last?.id {
                            Divider().opacity(0.5)
                        }
                    }
                }
            }
        }
    }

    // MARK: 资金信号列表

    private var signalList: some View {
        let items = viewModel.sortedSignals
        return ADCard(compact: true) {
            VStack(alignment: .leading, spacing: 0) {
                if items.isEmpty {
                    emptyHint("暂无资金信号")
                } else {
                    ForEach(items) { item in
                        HStack(spacing: AppTheme.Spacing.sm) {
                            VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                                Text(item.tsCode)
                                    .font(AppTheme.Typography.numericCallout)
                                    .foregroundStyle(AppTheme.Colors.textPrimary)
                                HStack(spacing: AppTheme.Spacing.sm) {
                                    signalChip("主力", item.mainNetInflow, isMoney: true)
                                    signalChip("两融", item.marginNetChange, isMoney: true)
                                    signalChip("龙虎榜", item.lhbNetBuy, isMoney: true)
                                }
                            }
                            Spacer(minLength: AppTheme.Spacing.sm)
                            VStack(alignment: .trailing, spacing: AppTheme.Spacing.xxs) {
                                Text(item.compositeScore.map { String(format: "%.1f", $0) } ?? "—")
                                    .font(AppTheme.Typography.title3.monospacedDigit())
                                    .foregroundStyle(AppTheme.Colors.changeColor(item.compositeScore))
                                Text("综合分")
                                    .font(AppTheme.Typography.caption)
                                    .foregroundStyle(AppTheme.Colors.textMuted)
                            }
                        }
                        .padding(.vertical, AppTheme.Spacing.sm)
                        .adHoverRow()
                        if item.id != items.last?.id {
                            Divider().opacity(0.5)
                        }
                    }
                }
            }
        }
    }

    private func signalChip(_ label: String, _ value: Double?, isMoney: Bool) -> some View {
        HStack(spacing: 3) {
            Text(label)
            Text(isMoney ? FundFlowFormat.money(value, digits: 1) : FundFlowFormat.pct(value))
                .foregroundStyle(AppTheme.Colors.changeColor(value))
        }
        .font(AppTheme.Typography.caption.monospacedDigit())
        .foregroundStyle(AppTheme.Colors.textSecondary)
    }

    private func emptyHint(_ text: String) -> some View {
        Text(text)
            .font(AppTheme.Typography.callout)
            .foregroundStyle(AppTheme.Colors.textMuted)
            .frame(maxWidth: .infinity, alignment: .center)
            .padding(.vertical, AppTheme.Spacing.lg)
    }
}
