import SwiftUI

/// 行情总览（iOS 主 tab）：加密实时行情列表 + 二级模块入口。
///
/// 契约：GET /crypto（实时价 enrich）。入口卡用 NavigationLink(value:)
/// 推入当前 NavigationStack（iOS tab 栈 / macOS 详情栈共用同一套路由登记）。
struct MarketsView: View {
    @State private var viewModel = MarketsViewModel()

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

    // MARK: - 二级模块入口

    private var entrySection: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            entryCard(section: .instruments, subtitle: "标的搜索")
            entryCard(section: .sectors, subtitle: "板块轮动")
            entryCard(section: .sentiment, subtitle: "情绪雷达")
        }
    }

    private func entryCard(section: AppSection, subtitle: String) -> some View {
        NavigationLink(value: AppRoute.section(section)) {
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
            .padding(.vertical, AppTheme.Spacing.lg)
            .background(
                RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                    .fill(AppTheme.Colors.elevated)
            )
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                    .strokeBorder(AppTheme.Colors.border, lineWidth: 0.5)
            )
        }
        .buttonStyle(.plain)
    }

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
                Button(option.label) {
                    Haptics.selection()
                    withAnimation(AppTheme.Motion.standard) {
                        viewModel.sort = option
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
            } else {
                ForEach(viewModel.sortedItems) { item in
                    cryptoCell(item)
                }
            }
        }
    }

    private func cryptoCell(_ item: CryptoInfo) -> some View {
        ADCard(padding: AppTheme.Spacing.md) {
            HStack(spacing: AppTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text(item.displayName)
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineLimit(1)
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Text(item.code)
                            .font(AppTheme.Typography.numericCallout)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                        // 契约无市值字段（web 端同），展示 24h 成交量代替
                        if let volume = item.volume24h, volume > 0 {
                            Text("24h量 \(NumberFormatting.signedMoney(volume))")
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.textMuted)
                        }
                    }
                }
                Spacer(minLength: AppTheme.Spacing.sm)
                VStack(alignment: .trailing, spacing: AppTheme.Spacing.xs) {
                    Text(priceText(item.price))
                        .font(AppTheme.Typography.numericCallout.weight(.medium))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    ChangeText(value: item.changePct)
                }
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
