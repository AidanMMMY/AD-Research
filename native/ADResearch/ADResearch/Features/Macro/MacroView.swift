import SwiftUI

/// 宏观：实时全球指数墙 + 分区指标快照（cn/us/eu/global）。
///
/// 布局：iOS 单列；macOS 指数墙自适应网格 + 分区双栏。
/// 点击指标进 ``MacroDetailView``（路由 AppRoute.macroDetail(code)）。
struct MacroView: View {
    @Environment(AppState.self) private var appState
    @State private var viewModel = MacroViewModel()

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                if viewModel.staleCount > 0 {
                    staleBanner
                }
                indicesWall
                regionSections
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.md)
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("宏观")
        .refreshable {
            await viewModel.load()
        }
        .task {
            await viewModel.loadIfNeeded()
        }
        #if os(macOS)
        .onReceive(NotificationCenter.default.publisher(for: .adRefreshRequested)) { _ in
            Task { await viewModel.load() }
        }
        #endif
    }

    // MARK: - 陈旧度横幅

    private var staleBanner: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "clock.badge.exclamationmark")
                .foregroundStyle(AppTheme.Colors.warning)
            Text("\(viewModel.staleCount) 项指数数据超过 24 小时未更新")
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.warning)
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                .fill(AppTheme.Colors.warning.opacity(0.10))
        )
    }

    // MARK: - 实时指数墙

    @ViewBuilder
    private var indicesWall: some View {
        switch viewModel.state {
        case .idle, .loading:
            skeletonGrid
        case .failed(let message):
            LoadErrorView(message: message) {
                Task { await viewModel.load() }
            }
        case .loaded:
            if !viewModel.indices.isEmpty {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    ADCardHeader(title: "实时指数", systemImage: "chart.xyaxis.line")
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: 104), spacing: AppTheme.Spacing.sm)],
                        spacing: AppTheme.Spacing.sm
                    ) {
                        ForEach(viewModel.indices) { item in
                            indexTile(item)
                        }
                    }
                }
            }
        }
    }

    private func indexTile(_ item: GlobalIndexRealtimeItem) -> some View {
        Button {
            Haptics.selection()
            appState.navigate(to: .macro, route: .macroDetail(item.code))
        } label: {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text(item.nameZh ?? item.code)
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                    .lineLimit(1)
                Text(NumberFormatting.tileValue(item.value, unit: item.unit ?? ""))
                    .font(AppTheme.Typography.numericCallout)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                ChangeText(value: item.changePct, font: AppTheme.Typography.caption.monospacedDigit())
            }
            .padding(AppTheme.Spacing.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                    .fill(AppTheme.Colors.surface)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: - 分区指标

    @ViewBuilder
    private var regionSections: some View {
        if case .loaded = viewModel.state {
            ForEach(viewModel.groups) { group in
                VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                    ADCardHeader(title: group.title, systemImage: regionIcon(group.region))
                    ADCard(padding: 0) {
                        LazyVStack(spacing: 0) {
                            ForEach(Array(group.items.enumerated()), id: \.element.id) { index, item in
                                macroRow(item)
                                if index < group.items.count - 1 {
                                    Divider()
                                        .overlay(AppTheme.Colors.border)
                                        .padding(.leading, AppTheme.Spacing.lg)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    private func macroRow(_ item: MacroLatestItem) -> some View {
        Button {
            Haptics.selection()
            appState.navigate(to: .macro, route: .macroDetail(item.code))
        } label: {
            HStack(spacing: AppTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                    Text(item.nameZh)
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    Text("\(item.period) · \(item.source)")
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: AppTheme.Spacing.xxs) {
                    Text(NumberFormatting.tileValue(item.value, unit: item.unit ?? ""))
                        .font(AppTheme.Typography.numericCallout)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                    if let changePct = item.changePct {
                        ChangeText(value: changePct, font: AppTheme.Typography.caption.monospacedDigit())
                    }
                }
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.md)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func regionIcon(_ region: String) -> String {
        switch region {
        case "cn": return "building.columns"
        case "us": return "dollarsign.circle"
        case "eu": return "eurosign.circle"
        default: return "globe"
        }
    }

    private var skeletonGrid: some View {
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 104), spacing: AppTheme.Spacing.sm)],
            spacing: AppTheme.Spacing.sm
        ) {
            ForEach(0..<8, id: \.self) { _ in
                SkeletonBlock(height: 64, cornerRadius: AppTheme.Radius.control)
            }
        }
    }
}

#Preview {
    NavigationStack {
        MacroView()
            .environment(AppState())
    }
}
