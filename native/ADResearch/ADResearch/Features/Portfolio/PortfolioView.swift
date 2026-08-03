import SwiftUI

/// 组合：自选标的（最新价/涨跌幅）+ 标的池。
///
/// iOS：列表左滑移除自选；macOS：右键菜单移除。点按行进标的详情
/// （AppRoute.instrumentDetail）。空态引导去标的模块添加。
struct PortfolioView: View {
    @State private var viewModel = PortfolioViewModel()

    var body: some View {
        content
            .background(AppTheme.Colors.background)
            .navigationTitle("组合")
            .task {
                await viewModel.loadIfNeeded()
            }
            #if os(macOS)
            .onReceive(NotificationCenter.default.publisher(for: .adRefreshRequested)) { _ in
                Task { await viewModel.load() }
            }
            #endif
    }

    @ViewBuilder
    private var content: some View {
        switch viewModel.state {
        case .idle, .loading:
            skeletonList
        case .failed(let message):
            ScrollView {
                LoadErrorView(message: message) {
                    Task { await viewModel.load() }
                }
                .padding(AppTheme.Spacing.lg)
            }
            .refreshable { await viewModel.load() }
        case .loaded:
            loadedList
        }
    }

    // MARK: - 已加载

    private var loadedList: some View {
        List {
            Section {
                if viewModel.favorites.isEmpty {
                    favoritesEmpty
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                } else {
                    ForEach(viewModel.favorites) { item in
                        favoriteRow(item)
                            .listRowSeparator(.hidden)
                            .listRowBackground(Color.clear)
                            .listRowInsets(EdgeInsets(
                                top: AppTheme.Spacing.xs,
                                leading: AppTheme.Spacing.lg,
                                bottom: AppTheme.Spacing.xs,
                                trailing: AppTheme.Spacing.lg
                            ))
                    }
                }
            } header: {
                sectionHeader("自选标的", systemImage: "star")
            }

            Section {
                if viewModel.pools.isEmpty {
                    Text("还没有标的池")
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                } else {
                    ForEach(viewModel.pools) { pool in
                        poolRow(pool)
                            .listRowSeparator(.hidden)
                            .listRowBackground(Color.clear)
                            .listRowInsets(EdgeInsets(
                                top: AppTheme.Spacing.xs,
                                leading: AppTheme.Spacing.lg,
                                bottom: AppTheme.Spacing.xs,
                                trailing: AppTheme.Spacing.lg
                            ))
                    }
                }
            } header: {
                sectionHeader("标的池", systemImage: "tray.full")
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .refreshable { await viewModel.load() }
        .animation(AppTheme.Motion.content, value: viewModel.favorites.count)
    }

    private func sectionHeader(_ title: String, systemImage: String) -> some View {
        Label(title, systemImage: systemImage)
            .font(AppTheme.Typography.cardTitle)
            .foregroundStyle(AppTheme.Colors.textPrimary)
            .symbolRenderingMode(.hierarchical)
            .textCase(nil)
    }

    // MARK: - 自选行

    private func favoriteRow(_ item: FavoriteItem) -> some View {
        let snapshot = viewModel.snapshot(for: item.etfCode)

        return NavigationLink(value: AppRoute.instrumentDetail(item.etfCode)) {
            ADCard(padding: AppTheme.Spacing.md) {
                HStack(spacing: AppTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                        Text(item.etfName ?? snapshot?.etfName ?? item.etfCode)
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .lineLimit(1)
                        HStack(spacing: AppTheme.Spacing.sm) {
                            Text(item.etfCode)
                                .font(AppTheme.Typography.caption.monospacedDigit())
                                .foregroundStyle(AppTheme.Colors.textMuted)
                            if let market = item.market, !market.isEmpty {
                                Text(market)
                                    .font(AppTheme.Typography.caption)
                                    .foregroundStyle(AppTheme.Colors.textSecondary)
                                    .padding(.horizontal, AppTheme.Spacing.sm)
                                    .padding(.vertical, AppTheme.Spacing.xxs)
                                    .background(
                                        Capsule(style: .continuous).fill(AppTheme.Colors.surface)
                                    )
                            }
                        }
                    }
                    Spacer(minLength: AppTheme.Spacing.sm)
                    VStack(alignment: .trailing, spacing: AppTheme.Spacing.xs) {
                        Text(NumberFormatting.tileValue(snapshot?.close))
                            .font(AppTheme.Typography.numericBody)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                        ChangeText(value: snapshot?.changePct)
                    }
                }
            }
        }
        .buttonStyle(.plain)
        .simultaneousGesture(TapGesture().onEnded {
            Haptics.selection()
        })
        #if os(iOS)
        .swipeActions(edge: .trailing) {
            Button(role: .destructive) {
                Task { await viewModel.removeFavorite(item) }
            } label: {
                Label("移除", systemImage: "star.slash")
            }
        }
        #endif
        #if os(macOS)
        .contextMenu {
            Button(role: .destructive) {
                Task { await viewModel.removeFavorite(item) }
            } label: {
                Label("移除自选", systemImage: "star.slash")
            }
        }
        #endif
    }

    private var favoritesEmpty: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            EmptyStateView(
                systemImage: "star",
                title: "还没有自选标的",
                description: "去「标的」模块把感兴趣的标的加入自选，\n这里会跟踪它们的最新价与涨跌幅"
            )
            NavigationLink(value: AppRoute.section(.instruments)) {
                Label("去标的模块看看", systemImage: "arrow.right")
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.accent)
                    .padding(.horizontal, AppTheme.Spacing.lg)
                    .padding(.vertical, AppTheme.Spacing.sm)
                    .background(
                        Capsule(style: .continuous).fill(AppTheme.Colors.accentSoft)
                    )
            }
            .buttonStyle(.plain)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - 标的池行

    private func poolRow(_ pool: InstrumentPool) -> some View {
        ADCard(padding: AppTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                HStack(spacing: AppTheme.Spacing.sm) {
                    Text(pool.name)
                        .font(AppTheme.Typography.cardTitle)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineLimit(1)
                    if pool.isPreset {
                        Text("预置")
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.accent)
                            .padding(.horizontal, AppTheme.Spacing.sm)
                            .padding(.vertical, AppTheme.Spacing.xxs)
                            .background(
                                Capsule(style: .continuous).fill(AppTheme.Colors.accentSoft)
                            )
                    }
                    Spacer()
                    Text("\(pool.members.count) 只")
                        .font(AppTheme.Typography.caption.monospacedDigit())
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
                if let description = pool.description, !description.isEmpty {
                    Text(description)
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .lineLimit(2)
                }
                let memberNames = pool.members.prefix(4).map {
                    $0.nameZh ?? $0.etfName ?? $0.etfCode
                }
                if !memberNames.isEmpty {
                    Text(memberNames.joined(separator: "、"))
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                        .lineLimit(1)
                }
            }
        }
    }

    // MARK: - 骨架屏

    private var skeletonList: some View {
        List {
            ForEach(0..<4, id: \.self) { _ in
                ADCard(padding: AppTheme.Spacing.md) {
                    HStack {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                            SkeletonBlock(height: 16).frame(width: 140)
                            SkeletonBlock(height: 10).frame(width: 90)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: AppTheme.Spacing.sm) {
                            SkeletonBlock(height: 16).frame(width: 70)
                            SkeletonBlock(height: 12).frame(width: 56)
                        }
                    }
                }
                .listRowSeparator(.hidden)
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets(
                    top: AppTheme.Spacing.xs,
                    leading: AppTheme.Spacing.lg,
                    bottom: AppTheme.Spacing.xs,
                    trailing: AppTheme.Spacing.lg
                ))
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .scrollDisabled(true)
    }
}

#Preview {
    NavigationStack {
        PortfolioView()
    }
}
