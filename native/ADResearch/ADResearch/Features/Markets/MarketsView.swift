import SwiftUI

/// 行情总览（iOS 主 tab）：加密实时行情列表 + 二级模块入口。
///
/// 契约：GET /crypto（实时价 enrich）。入口卡用 NavigationLink(value:)
/// 推入当前 NavigationStack（iOS tab 栈 / macOS 详情栈共用同一套路由登记）。
///
/// - 搜索：``.searchable``（macOS 自动进 toolbar 白得 ⌘F）。列表一次取全
///   200 条（后端 page_size 上限），过滤在客户端完成，无需防抖。
/// - 自动刷新：页面可见期间 30s 静默轮询（``refreshQuietly`` 不回退骨架态），
///   页面消失（onDisappear）即停表。
/// - 密度：iOS 卡片流；macOS 紧凑行式（hairline 分隔，行高 ~44pt），
///   入口卡收成一行紧凑链接条。
struct MarketsView: View {
    @State private var viewModel = MarketsViewModel()
    @State private var searchText = ""
    @State private var autoRefreshTask: Task<Void, Never>?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                entrySection
                cryptoSection
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.md)
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("行情")
        .searchable(text: $searchText, prompt: "搜索币种 / 代码")
        .refreshable {
            await viewModel.reload()
        }
        .task {
            await viewModel.loadIfNeeded()
        }
        .onAppear { startAutoRefresh() }
        .onDisappear { stopAutoRefresh() }
        #if os(macOS)
        .onReceive(NotificationCenter.default.publisher(for: .adRefreshRequested)) { _ in
            Task { await viewModel.reload() }
        }
        #endif
    }

    // MARK: - 自动刷新（30s，前台可见期间）

    private func startAutoRefresh() {
        guard autoRefreshTask == nil else { return }
        autoRefreshTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30_000_000_000)
                guard !Task.isCancelled else { return }
                await viewModel.refreshQuietly()
            }
        }
    }

    private func stopAutoRefresh() {
        autoRefreshTask?.cancel()
        autoRefreshTask = nil
    }

    /// 搜索过滤后的展示序列（全量已在本地，客户端过滤）
    private var visibleItems: [CryptoInfo] {
        let keyword = searchText.trimmingCharacters(in: .whitespaces)
        let sorted = viewModel.sortedItems
        guard !keyword.isEmpty else { return sorted }
        return sorted.filter {
            $0.code.localizedCaseInsensitiveContains(keyword)
                || $0.name.localizedCaseInsensitiveContains(keyword)
                || ($0.nameZh?.localizedCaseInsensitiveContains(keyword) ?? false)
        }
    }

    // MARK: - 二级模块入口

    #if os(macOS)
    /// macOS：一行紧凑链接条（单张 ADCard + 分隔线）
    private var entrySection: some View {
        ADCard(padding: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.sm) {
                entryLink(section: .instruments, subtitle: "标的搜索")
                Divider().frame(height: 20)
                entryLink(section: .sectors, subtitle: "板块轮动")
                Divider().frame(height: 20)
                entryLink(section: .sentiment, subtitle: "情绪雷达")
            }
        }
    }

    private func entryLink(section: AppSection, subtitle: String) -> some View {
        NavigationLink(value: AppRoute.section(section)) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: section.systemImage)
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.accent)
                    .symbolRenderingMode(.hierarchical)
                Text(section.title)
                    .font(AppTheme.Typography.callout.weight(.medium))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text(subtitle)
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                    .lineLimit(1)
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.system(size: 9))
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, AppTheme.Spacing.xs)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity)
    }
    #else
    /// iOS：三张入口卡（复用 ADCard）
    private var entrySection: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            entryCard(section: .instruments, subtitle: "标的搜索")
            entryCard(section: .sectors, subtitle: "板块轮动")
            entryCard(section: .sentiment, subtitle: "情绪雷达")
        }
    }

    private func entryCard(section: AppSection, subtitle: String) -> some View {
        NavigationLink(value: AppRoute.section(section)) {
            ADCard(padding: AppTheme.Spacing.lg) {
                VStack(spacing: AppTheme.Spacing.sm) {
                    Image(systemName: section.systemImage)
                        .font(.title3)
                        .foregroundStyle(AppTheme.Colors.accent)
                        .symbolRenderingMode(.hierarchical)
                    VStack(spacing: AppTheme.Spacing.xxs) {
                        Text(section.title)
                            .font(AppTheme.Typography.callout.weight(.medium))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                        Text(subtitle)
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textMuted)
                    }
                }
                .frame(maxWidth: .infinity)
            }
        }
        .buttonStyle(.plain)
    }
    #endif

    // MARK: - 加密行情

    private var cryptoSection: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(alignment: .firstTextBaseline) {
                Text("加密行情")
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                if let lastUpdated = viewModel.lastUpdated {
                    Text("更新于 \(DateFormatting.relative(lastUpdated))")
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
                Spacer()
                sortMenu
            }
            cryptoContent
        }
    }

    private var sortMenu: some View {
        Menu {
            ForEach(MarketsViewModel.SortOption.allCases) { option in
                Button {
                    Haptics.selection()
                    withAnimation(AppTheme.Motion.standard) {
                        viewModel.sort = option
                    }
                } label: {
                    if viewModel.sort == option {
                        Label(option.label, systemImage: "checkmark")
                    } else {
                        Text(option.label)
                    }
                }
            }
        } label: {
            HStack(spacing: AppTheme.Spacing.xs) {
                Text(viewModel.sort.label).font(AppTheme.Typography.caption)
                Image(systemName: "arrow.up.arrow.down").font(.system(size: 9))
            }
            .foregroundStyle(AppTheme.Colors.textSecondary)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.xs)
            .background(Capsule(style: .continuous).fill(AppTheme.Colors.surface))
        }
    }

    @ViewBuilder
    private var cryptoContent: some View {
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
                    systemImage: "bitcoinsign.circle",
                    title: "暂无加密行情",
                    description: "稍后下拉刷新试试"
                )
            } else if visibleItems.isEmpty {
                EmptyStateView(
                    systemImage: "magnifyingglass",
                    title: "没有匹配的币种",
                    description: "换个关键词试试"
                )
            } else {
                #if os(macOS)
                // macOS：行式紧凑列表（hairline 分隔，垂直 padding 减半）
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(visibleItems.enumerated()), id: \.element.id) { index, item in
                        cryptoRow(item)
                        if index < visibleItems.count - 1 {
                            Divider()
                        }
                    }
                }
                #else
                ForEach(visibleItems) { item in
                    cryptoCell(item)
                }
                #endif
            }
        }
    }

    /// iOS 卡片行
    private func cryptoCell(_ item: CryptoInfo) -> some View {
        ADCard(padding: AppTheme.Spacing.md) {
            cryptoRowContent(item)
        }
    }

    /// macOS 紧凑行（无卡片，行高约 44pt）
    private func cryptoRow(_ item: CryptoInfo) -> some View {
        cryptoRowContent(item)
            .padding(.vertical, AppTheme.Spacing.xs)
            .padding(.horizontal, AppTheme.Spacing.xs)
            .contentShape(Rectangle())
    }

    /// 行内容（双端共用）：名称+代码 | 现价+24h 涨跌
    private func cryptoRowContent(_ item: CryptoInfo) -> some View {
        HStack(spacing: AppTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                Text(item.displayName)
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                HStack(spacing: AppTheme.Spacing.sm) {
                    Text(item.code)
                        .font(AppTheme.Typography.caption.monospacedDigit())
                        .foregroundStyle(AppTheme.Colors.textMuted)
                    // 契约无市值字段（web 端同），展示 24h 成交量代替
                    if let volume = item.volume24h, volume > 0 {
                        Text("24h量 \(NumberFormatting.signedMoney(volume))")
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textMuted)
                    }
                }
            }
            .layoutPriority(1)
            Spacer(minLength: AppTheme.Spacing.sm)
            VStack(alignment: .trailing, spacing: AppTheme.Spacing.xxs) {
                Text(priceText(item.price))
                    .font(AppTheme.Typography.numericCallout.weight(.medium))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                ChangeText(value: item.changePct)
            }
        }
    }

    /// 加密价格精度（对齐 web formatCryptoPrice：小额币种 6 位小数）
    private func priceText(_ price: Double?) -> String {
        guard let price else { return "—" }
        if price < 0.01 { return String(format: "$%.6f", price) }
        if price < 1 { return String(format: "$%.4f", price) }
        return "$" + NumberFormatting.tileValue(price)
    }

    private var skeleton: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            ForEach(0..<6, id: \.self) { _ in
                ADCard(padding: AppTheme.Spacing.md) {
                    HStack {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                            SkeletonBlock(height: 14).frame(width: 120)
                            SkeletonBlock(height: 10).frame(width: 80)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: AppTheme.Spacing.sm) {
                            SkeletonBlock(height: 14).frame(width: 90)
                            SkeletonBlock(height: 10).frame(width: 60)
                        }
                    }
                }
            }
        }
    }
}

#Preview {
    NavigationStack {
        MarketsView()
    }
}
