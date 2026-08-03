import SwiftUI

/// 评分榜：全市场综合评分排名（默认模板，Crypto 除外）。
///
/// 契约见 ``ScoreRankingViewModel``。行点击 → 标的详情（评分卡全维度）。
struct ScoreRankingView: View {
    @State private var viewModel = ScoreRankingViewModel()
    @Environment(AppState.self) private var appState
    #if os(macOS)
    @State private var highlightedIndex: Int?
    #endif

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    filterBar
                    content
                }
                .padding(.horizontal, AppTheme.Spacing.lg)
                .padding(.vertical, AppTheme.Spacing.md)
            }
            #if os(macOS)
            .background(
                ADKeyboardNavButtons(
                    count: viewModel.items.count,
                    highlighted: $highlightedIndex
                ) { index in
                    guard viewModel.items.indices.contains(index) else { return }
                    appState.navigate(to: .instruments, route: .instrumentDetail(viewModel.items[index].etfCode))
                }
            )
            .onChange(of: highlightedIndex) { _, newValue in
                guard let newValue, viewModel.items.indices.contains(newValue) else { return }
                withAnimation(AppTheme.Motion.fade) {
                    proxy.scrollTo(viewModel.items[newValue].etfCode, anchor: .center)
                }
            }
            .onChange(of: viewModel.items.count) { _, newCount in
                if let highlightedIndex, highlightedIndex >= newCount {
                    self.highlightedIndex = nil
                }
            }
            #endif
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("评分榜")
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
            filterMenu(
                title: viewModel.market.label,
                options: ScoreRankingViewModel.MarketFilter.allCases,
                current: viewModel.market
            ) { viewModel.market = $0 }
            filterMenu(
                title: viewModel.typeFilter.label,
                options: ScoreRankingViewModel.TypeFilter.allCases,
                current: viewModel.typeFilter
            ) { viewModel.typeFilter = $0 }
            Spacer()
            if let date = viewModel.tradeDate {
                Text("评分日 \(date)")
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
        }
    }

    private func filterMenu<Option: Identifiable & Hashable>(
        title: String,
        options: [Option],
        current: Option,
        onSelect: @escaping (Option) -> Void
    ) -> some View where Option: RawRepresentable, Option.RawValue == String {
        Menu {
            ForEach(options) { option in
                Button(labelOf(option)) { onSelect(option) }
            }
        } label: {
            HStack(spacing: AppTheme.Spacing.xs) {
                Text(title).font(AppTheme.Typography.caption)
                Image(systemName: "chevron.down").font(.system(size: 9))
            }
            .foregroundStyle(AppTheme.Colors.textSecondary)
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, AppTheme.Spacing.xs)
            .background(Capsule().fill(AppTheme.Colors.elevated))
            .overlay(Capsule().strokeBorder(AppTheme.Colors.border, lineWidth: 0.5))
        }
        .menuStyle(.borderlessButton)
    }

    private func labelOf<Option>(_ option: Option) -> String {
        // MarketFilter/TypeFilter 均有 label；经反射取避免泛型约束膨胀
        (option as? ScoreRankingViewModel.MarketFilter)?.label
            ?? (option as? ScoreRankingViewModel.TypeFilter)?.label
            ?? String(describing: option)
    }

    // MARK: - 榜单内容

    @ViewBuilder
    private var content: some View {
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
            if viewModel.items.isEmpty {
                ADCard {
                    Text("暂无评分数据")
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                        .frame(maxWidth: .infinity, alignment: .center)
                }
            } else {
                rankingList
            }
        }
    }

    private var rankingList: some View {
        ADCard(compact: true) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(viewModel.items.enumerated()), id: \.element.etfCode) { index, item in
                    Button {
                        appState.navigate(to: .instruments, route: .instrumentDetail(item.etfCode))
                    } label: {
                        rankingRow(index: index, item: item)
                    }
                    .buttonStyle(.plain)
                    #if os(macOS)
                    .adKeyboardHighlight(highlightedIndex == index)
                    #endif
                    .adHoverRow()
                    .id(item.etfCode)
                    if item.etfCode != viewModel.items.last?.etfCode {
                        Divider().opacity(0.5)
                    }
                }
            }
        }
    }

    private func rankingRow(index: Int, item: InstrumentScore) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            // 名次：前三 accent 强调
            Text("\(index + 1)")
                .font(AppTheme.Typography.numericCallout.weight(index < 3 ? .bold : .regular))
                .foregroundStyle(index < 3 ? AppTheme.Colors.accent : AppTheme.Colors.textMuted)
                .frame(width: 28, alignment: .trailing)

            VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                Text(item.displayName ?? item.etfCode)
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                HStack(spacing: AppTheme.Spacing.xs) {
                    Text(item.etfCode)
                    if let market = item.market {
                        Text("· \(market)")
                    }
                    if let category = item.category {
                        Text("· \(category)")
                    }
                }
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
                .lineLimit(1)
            }

            Spacer(minLength: AppTheme.Spacing.sm)

            // 近 1 月收益
            Text(item.return1m.map { String(format: "%@%.1f%%", $0 > 0 ? "+" : "", $0) } ?? "—")
                .font(AppTheme.Typography.caption.monospacedDigit())
                .foregroundStyle(AppTheme.Colors.changeColor(item.return1m))
                .frame(width: 56, alignment: .trailing)

            // 综合分 + 细条
            VStack(alignment: .trailing, spacing: 3) {
                Text(item.compositeScore.map { String(format: "%.1f", $0) } ?? "—")
                    .font(AppTheme.Typography.numericCallout.weight(.semibold))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                scoreBar(item.compositeScore)
            }
            .frame(width: 64, alignment: .trailing)
        }
        .padding(.vertical, AppTheme.Spacing.sm)
        .contentShape(Rectangle())
    }

    private func scoreBar(_ score: Double?) -> some View {
        let ratio = min(max((score ?? 0) / 100, 0), 1)
        return GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(AppTheme.Colors.border.opacity(0.4))
                Capsule().fill(AppTheme.Colors.accent.opacity(0.75))
                    .frame(width: geo.size.width * ratio)
            }
        }
        .frame(height: 3)
    }
}
