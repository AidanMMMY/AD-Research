import Charts
import SwiftUI

/// 标的详情：hero 价格 + 综合评分卡 + 走势图（十字光标）+ 相关资讯 + 分组基本信息。
///
/// 路由：AppRoute.instrumentDetail(code)。
/// 契约：GET /etfs/{code} + GET /etfs/{code}/sparkline?days= + GET /scores/{code}
/// + GET/POST /favorites/{code}/status|toggle + GET /news?symbol=。
///
/// 注：基本信息与 sparkline 状态机仍在 ``InstrumentDetailViewModel``
/// （InstrumentsViewModel.swift，本任务不可改）；评分/自选/资讯的增强状态
/// 收在下方 ``InstrumentDetailExtrasViewModel``，两者并行加载互不阻塞。
struct InstrumentDetailView: View {
    let code: String
    @Environment(AppState.self) private var appState
    @State private var viewModel: InstrumentDetailViewModel
    @State private var extras: InstrumentDetailExtrasViewModel
    /// 十字光标选中的数据点下标（chartXSelection，iOS 17 / macOS 14+）
    @State private var selectedIndex: Int?

    init(code: String) {
        self.code = code
        _viewModel = State(initialValue: InstrumentDetailViewModel(code: code))
        _extras = State(initialValue: InstrumentDetailExtrasViewModel(code: code))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                headerCard
                scoreCard
                rangePicker
                chartArea
                relatedNewsCard
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
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                favoriteButton
            }
        }
        .refreshable {
            await reloadAll()
        }
        .task {
            async let base: () = viewModel.loadIfNeeded()
            async let extra: () = extras.loadIfNeeded()
            _ = await (base, extra)
        }
    }

    private func reloadAll() async {
        async let base: () = viewModel.reload()
        async let extra: () = extras.reload()
        _ = await (base, extra)
    }

    // MARK: - 加自选星标（乐观翻转 + 失败回滚 + Haptics）

    private var favoriteButton: some View {
        Button {
            Task { await extras.toggleFavorite() }
        } label: {
            Image(systemName: extras.isFavorite ? "star.fill" : "star")
                .foregroundStyle(AppTheme.Colors.accent)
                .symbolRenderingMode(.hierarchical)
                .contentTransition(.symbolEffect(.replace))
        }
        .disabled(extras.isTogglingFavorite)
        .accessibilityLabel(extras.isFavorite ? "移出自选" : "加入自选")
    }

    // MARK: - 头部卡（名称 + hero 价格 + 涨跌额/涨跌幅）

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
                    Task { await reloadAll() }
                }
            }
        case .loaded:
            if let info = viewModel.info {
                ADCard {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        Text(info.displayName)
                            .font(AppTheme.Typography.pageTitle)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
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
                        if let latest = viewModel.points.last {
                            HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.md) {
                                // hero 价格：34pt 等宽大字（AppTheme.Typography.display 已由 W3 提供）
                                Text(priceText(latest))
                                    .font(AppTheme.Typography.display)
                                    .foregroundStyle(AppTheme.Colors.textPrimary)
                                Spacer()
                                // 涨跌额 / 涨跌幅并排（日涨跌：末点 vs 前一点）
                                if let dayChange {
                                    VStack(alignment: .trailing, spacing: AppTheme.Spacing.xxs) {
                                        Text(NumberFormatting.percent(dayChange.pct))
                                            .font(AppTheme.Typography.numericCallout.weight(.semibold))
                                            .foregroundStyle(AppTheme.Colors.changeColor(dayChange.pct))
                                        Text(signedAmount(dayChange.amount))
                                            .font(AppTheme.Typography.numericCallout)
                                            .foregroundStyle(AppTheme.Colors.changeColor(dayChange.pct))
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    /// 日涨跌（末点 vs 前一点）；序列不足两点时回落为首末区间涨跌
    private var dayChange: (amount: Double, pct: Double)? {
        let values = viewModel.points
        guard let last = values.last else { return nil }
        if values.count >= 2 {
            let previous = values[values.count - 2]
            guard previous > 0 else { return nil }
            return (last - previous, (last - previous) / previous * 100)
        }
        guard let first = values.first, first > 0 else { return nil }
        return (last - first, (last - first) / first * 100)
    }

    private func priceText(_ value: Double) -> String {
        let currency = viewModel.info?.currency ?? ""
        let formatted = NumberFormatting.tileValue(value)
        return currency.isEmpty ? formatted : "\(formatted) \(currency)"
    }

    /// 涨跌额带正负号（对齐 ChangeText 的符号语义）
    private func signedAmount(_ value: Double) -> String {
        String(format: "%@%.2f", value >= 0 ? "+" : "", value)
    }

    // MARK: - 综合评分卡（404 / 无数据 → 整卡隐藏）

    @ViewBuilder
    private var scoreCard: some View {
        switch extras.scoreState {
        case .idle, .loading:
            ADCard {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    SkeletonBlock(height: 16).frame(width: 96)
                    SkeletonBlock(height: 34).frame(width: 120)
                    SkeletonBlock(height: 8)
                    SkeletonBlock(height: 8)
                }
            }
        case .failed:
            // 评分是增强信息，失败不打断详情页主流程，静默隐藏
            EmptyView()
        case .loaded:
            if let score = extras.score {
                ADCard {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                        ADCardHeader(
                            title: "综合评分",
                            subtitle: score.tradeDate.map { "截至 \(DateFormatting.formatDate($0))" },
                            systemImage: "gauge.with.dots.needle.67percent"
                        )
                        HStack(alignment: .firstTextBaseline) {
                            Text(score.compositeScore.map { String(format: "%.1f", $0) } ?? "—")
                                .font(AppTheme.Typography.display)
                                .foregroundStyle(AppTheme.Colors.accent)
                            Text("/ 100")
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.textMuted)
                            Spacer()
                            VStack(alignment: .trailing, spacing: AppTheme.Spacing.xxs) {
                                if let rank = score.rankOverall {
                                    Text("全市场第 \(rank) 名")
                                        .font(AppTheme.Typography.numericCallout)
                                        .foregroundStyle(AppTheme.Colors.textSecondary)
                                }
                                if let rank = score.rankCategory {
                                    Text("分类内第 \(rank) 名")
                                        .font(AppTheme.Typography.caption)
                                        .foregroundStyle(AppTheme.Colors.textMuted)
                                }
                            }
                        }
                        VStack(spacing: AppTheme.Spacing.sm) {
                            scoreBar(label: "收益", value: score.scoreReturn)
                            scoreBar(label: "风险", value: score.scoreRisk)
                            scoreBar(label: "夏普", value: score.scoreSharpe)
                            scoreBar(label: "流动性", value: score.scoreLiquidity)
                            scoreBar(label: "趋势", value: score.scoreTrend)
                        }
                        if score.return1m != nil || score.return3m != nil || score.return1y != nil {
                            HStack(spacing: AppTheme.Spacing.lg) {
                                periodReturn(label: "近1月", value: score.return1m)
                                periodReturn(label: "近3月", value: score.return3m)
                                periodReturn(label: "近1年", value: score.return1y)
                                Spacer()
                            }
                        }
                    }
                }
            }
        }
    }

    /// 分项横向条形（0-100，accent 色，数值右对齐等宽）
    private func scoreBar(label: String, value: Double?) -> some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Text(label)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
                .frame(width: 40, alignment: .leading)
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(AppTheme.Colors.surface)
                    Capsule()
                        .fill(AppTheme.Colors.accent)
                        .frame(width: geometry.size.width * barFraction(value))
                }
            }
            .frame(height: 6)
            Text(value.map { String(format: "%.0f", $0) } ?? "—")
                .font(AppTheme.Typography.caption.monospacedDigit())
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .frame(width: 28, alignment: .trailing)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(label) \(value.map { String(format: "%.0f", $0) } ?? "无数据")")
    }

    private func barFraction(_ value: Double?) -> CGFloat {
        guard let value, !value.isNaN else { return 0 }
        return CGFloat(min(max(value, 0), 100) / 100)
    }

    private func periodReturn(label: String, value: Double?) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
            Text(label)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
            ChangeText(value: value, font: AppTheme.Typography.numericCallout)
        }
    }

    // MARK: - 区间切换

    private var rangePicker: some View {
        Picker("区间", selection: $viewModel.range) {
            ForEach(InstrumentDetailViewModel.RangeOption.allCases) { option in
                Text(option.label).tag(option)
            }
        }
        .pickerStyle(.segmented)
        .onChange(of: viewModel.range) { selectedIndex = nil }
    }

    // MARK: - 走势图（十字光标 + linear 插值 + minHeight 260 可延展）

    @ViewBuilder
    private var chartArea: some View {
        switch viewModel.chartState {
        case .idle, .loading:
            SkeletonBlock(height: 260, cornerRadius: AppTheme.Radius.card)
        case .failed(let message):
            LoadErrorView(message: message) {
                Task { await reloadAll() }
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
            // 金融折线禁止平滑插值（catmullRom 会虚构拐点）
            .interpolationMethod(.linear)

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
            .interpolationMethod(.linear)

            if let selectedIndex {
                RuleMark(x: .value("选中", selectedIndex))
                    .foregroundStyle(AppTheme.Colors.textMuted.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 3]))
            }
        }
        .chartXSelection(value: $selectedIndex)
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
        .frame(minHeight: 260)
        .overlay(alignment: .topLeading) {
            if let selectedIndex, values.indices.contains(selectedIndex) {
                selectionCallout(index: selectedIndex)
            }
        }
        .animation(AppTheme.Motion.content, value: values.count)
        .accessibilityLabel("收盘价走势图")
    }

    /// 十字光标浮层：该日日期 / 收盘价 / 日涨跌幅
    private func selectionCallout(index: Int) -> some View {
        let values = viewModel.points
        let dates = viewModel.dates
        let value = values[index]
        let dayChangePct: Double? = {
            guard index > 0, values[index - 1] > 0 else { return nil }
            return (value - values[index - 1]) / values[index - 1] * 100
        }()
        return HStack(spacing: AppTheme.Spacing.sm) {
            if dates.indices.contains(index) {
                Text(dates[index])
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
            Text(NumberFormatting.tileValue(value))
                .foregroundStyle(AppTheme.Colors.textPrimary)
            if let dayChangePct {
                Text(NumberFormatting.percent(dayChangePct))
                    .foregroundStyle(AppTheme.Colors.changeColor(dayChangePct))
            }
        }
        .font(AppTheme.Typography.caption.monospacedDigit())
        .padding(.horizontal, AppTheme.Spacing.sm)
        .padding(.vertical, AppTheme.Spacing.xs)
        .background(
            RoundedRectangle(cornerRadius: AppTheme.Radius.chip, style: .continuous)
                .fill(AppTheme.Colors.elevated)
                .shadow(color: .black.opacity(0.08), radius: 4, y: 1)
        )
        .padding(AppTheme.Spacing.sm)
        .transition(.opacity)
    }

    /// ``YYYY-MM-DD`` → ``M/d``
    private func shortDate(_ string: String) -> String {
        let parts = string.split(separator: "-")
        guard parts.count == 3,
              let month = Int(parts[1]),
              let day = Int(parts[2]) else { return string }
        return "\(month)/\(day)"
    }

    // MARK: - 相关资讯（newsList symbol=code 前 5 条；空态隐藏）

    @ViewBuilder
    private var relatedNewsCard: some View {
        switch extras.newsState {
        case .idle, .loading:
            ADCard {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    SkeletonBlock(height: 16).frame(width: 80)
                    ForEach(0..<3, id: \.self) { _ in
                        SkeletonBlock(height: 14)
                    }
                }
            }
        case .failed:
            // 资讯是增强信息，失败静默隐藏
            EmptyView()
        case .loaded:
            if !extras.relatedNews.isEmpty {
                ADCard {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                        ADCardHeader(title: "相关资讯", systemImage: "newspaper") {
                            Button {
                                Haptics.selection()
                                appState.navigate(to: .news, route: .section(.news))
                            } label: {
                                Text("查看全部")
                                    .font(AppTheme.Typography.caption)
                                    .foregroundStyle(AppTheme.Colors.accent)
                            }
                            .buttonStyle(.plain)
                        }
                        VStack(spacing: AppTheme.Spacing.sm) {
                            ForEach(extras.relatedNews) { article in
                                newsRow(article)
                            }
                        }
                    }
                }
            }
        }
    }

    private func newsRow(_ article: NewsArticle) -> some View {
        Button {
            Haptics.selection()
            appState.navigate(to: .news, route: .newsDetail(article.id))
        } label: {
            HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                    Text(article.displayTitle)
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .multilineTextAlignment(.leading)
                        .lineLimit(2)
                    HStack(spacing: AppTheme.Spacing.xs) {
                        Text(article.source)
                        Text("·")
                        Text(DateFormatting.relative(article.publishedAt))
                    }
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                }
                Spacer(minLength: AppTheme.Spacing.sm)
                Image(systemName: "chevron.right")
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: - 基本信息卡（规模与费率 / 跟踪与归属 / 基本信息 三段分组）

    @ViewBuilder
    private var infoCard: some View {
        if let info = viewModel.info {
            ADCard {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    ADCardHeader(title: "基本信息", systemImage: "info.circle")
                    infoSection("规模与费率", rows: [
                        ("基金规模", info.fundSize.map { NumberFormatting.signedMoney($0) }),
                        // 契约：expense_ratio 本身已是百分数（web 直接 toFixed(2)+"%"）
                        ("管理费率", info.expenseRatio.map { String(format: "%.2f%%", $0) }),
                        ("总市值", info.marketCap.map { NumberFormatting.signedMoney($0) }),
                    ])
                    infoSection("跟踪与归属", rows: [
                        ("跟踪指数", info.underlyingIndex),
                        ("基金公司", info.manager),
                        ("基金经理", info.fundManager),
                        ("行业", info.industry ?? info.sector),
                        ("国家/地区", info.country),
                    ])
                    infoSection("基本信息", rows: [
                        ("类别", info.category),
                        ("子类别", info.subCategory),
                        ("上市地", info.listingMarket),
                        ("板块", info.board),
                        ("成立日期", info.inceptionDate.map { DateFormatting.formatDate($0) }),
                    ])
                }
            }
        }
    }

    /// 单段分组：组内无有效行则整段隐藏
    @ViewBuilder
    private func infoSection(_ title: String, rows: [(String, String?)]) -> some View {
        let visible = rows.compactMap { label, value -> (String, String)? in
            guard let value, !value.isEmpty else { return nil }
            return (label, value)
        }
        if !visible.isEmpty {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Text(title)
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                LazyVGrid(
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
    }
}

// MARK: - 增强数据 ViewModel（评分 / 自选 / 相关资讯）

/// 标的详情增强数据仓库。与 ``InstrumentDetailViewModel``（基本信息+行情，
/// 本任务不可改）并行：三源独立容错，任何一路失败不影响详情页主流程。
///
/// 契约：
/// - GET /scores/{code}（InstrumentScore；404 = 无评分 → 整卡隐藏）
/// - GET /favorites/{code}/status + POST /favorites/{code}/toggle
/// - GET /news?symbol={code}&page_size=5（NewsListResponse）
@MainActor
@Observable
final class InstrumentDetailExtrasViewModel {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case failed(String)
    }

    let code: String

    private(set) var score: InstrumentScore?
    private(set) var scoreState: LoadState = .idle

    private(set) var isFavorite = false
    private(set) var isTogglingFavorite = false

    private(set) var relatedNews: [NewsArticle] = []
    private(set) var newsState: LoadState = .idle

    private var hasLoadedOnce = false

    init(code: String) {
        self.code = code
    }

    func loadIfNeeded() async {
        guard !hasLoadedOnce else { return }
        hasLoadedOnce = true
        await reload()
    }

    func reload() async {
        async let scoreTask: () = loadScore()
        async let favoriteTask: () = loadFavoriteStatus()
        async let newsTask: () = loadRelatedNews()
        _ = await (scoreTask, favoriteTask, newsTask)
    }

    private func loadScore() async {
        if score == nil { scoreState = .loading }
        do {
            score = try await APIClient.shared.send(.instrumentScore(code), as: InstrumentScore.self)
            scoreState = .loaded
        } catch let error as APIError {
            if error.isNotFound {
                // 404 = 无评分记录（对齐 isNotFound 空态模式），score 保持 nil → 整卡隐藏
                score = nil
                scoreState = .loaded
            } else {
                scoreState = .failed(error.userMessage)
            }
        } catch {
            scoreState = .failed("加载失败，请稍后重试")
        }
    }

    private func loadFavoriteStatus() async {
        // 状态查询失败静默（星标默认未选），toggle 时以服务端真实值为准
        if let status = try? await APIClient.shared.send(.favoriteStatus(code), as: FavoriteStatusResponse.self) {
            isFavorite = status.isFavorite
        }
    }

    /// 乐观翻转：先反转 UI + Haptics，失败回滚；成功以服务端响应为准
    func toggleFavorite() async {
        guard !isTogglingFavorite else { return }
        isTogglingFavorite = true
        let previous = isFavorite
        isFavorite.toggle()
        Haptics.selection()
        do {
            let response = try await APIClient.shared.send(.favoriteToggle(code), as: FavoriteToggleResponse.self)
            isFavorite = response.isFavorite
            Haptics.notify(success: true)
        } catch {
            isFavorite = previous
            Haptics.notify(success: false)
        }
        isTogglingFavorite = false
    }

    private func loadRelatedNews() async {
        if relatedNews.isEmpty { newsState = .loading }
        do {
            let response = try await APIClient.shared.send(
                .newsList(NewsListParams(symbol: code, page: 1, pageSize: 5)),
                as: NewsListResponse.self
            )
            relatedNews = response.items
            newsState = .loaded
        } catch let error as APIError {
            newsState = .failed(error.userMessage)
        } catch {
            newsState = .failed("加载失败，请稍后重试")
        }
    }
}

#Preview {
    NavigationStack {
        InstrumentDetailView(code: "510300.SH")
    }
    .environment(AppState())
}
