import SwiftUI

/// 标的库：全平台标的搜索 + 市场筛选 + 分页滚动加载。
///
/// iOS：单列卡片流（refreshable + 搜索防抖）；macOS：同构。
/// 点击进 ``InstrumentDetailView``（路由 AppRoute.instrumentDetail(code)）。
struct InstrumentsView: View {
    @Environment(AppState.self) private var appState
    @State private var viewModel = InstrumentsViewModel()
    @State private var searchText = ""
    @State private var searchTask: Task<Void, Never>?

    /// 市场筛选档（DB 值；nil = 全部）
    private static let marketOptions: [(title: String, value: String?)] = [
        ("全部", nil),
        ("A股", "A股"),
        ("美股", "US"),
        ("港股", "HK"),
        ("加密", "CRYPTO"),
    ]

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                filterBar
                contentList
            }
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.vertical, AppTheme.Spacing.md)
        }
        .background(AppTheme.Colors.background)
        .navigationTitle("标的")
        .refreshable {
            await viewModel.reload()
        }
        .task {
            await viewModel.loadIfNeeded()
        }
        .onChange(of: searchText) { _, newValue in
            // 300ms 防抖：输入停止后再发请求
            searchTask?.cancel()
            searchTask = Task {
                try? await Task.sleep(nanoseconds: 300_000_000)
                guard !Task.isCancelled else { return }
                await MainActor.run { viewModel.query = newValue.trimmingCharacters(in: .whitespaces) }
            }
        }
        #if os(macOS)
        .onReceive(NotificationCenter.default.publisher(for: .adRefreshRequested)) { _ in
            Task { await viewModel.reload() }
        }
        #endif
    }

    // MARK: - 筛选条

    private var filterBar: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(AppTheme.Colors.textMuted)
                TextField("搜索代码 / 名称", text: $searchText)
                    .textFieldStyle(.plain)
                if !searchText.isEmpty {
                    Button {
                        searchText = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(AppTheme.Colors.textMuted)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .background(
                RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                    .fill(AppTheme.Colors.surface)
            )

            HStack(spacing: AppTheme.Spacing.sm) {
                marketMenu
                Spacer()
                if viewModel.total > 0 {
                    Text("共 \(NumberFormatting.count(viewModel.total)) 只")
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
            }
        }
    }

    private var marketMenu: some View {
        Menu {
            ForEach(Self.marketOptions, id: \.title) { option in
                Button(option.title) { viewModel.market = option.value }
            }
        } label: {
            let current = Self.marketOptions.first { $0.value == viewModel.market }?.title ?? "全部"
            HStack(spacing: AppTheme.Spacing.xs) {
                Text(current).font(AppTheme.Typography.caption)
                Image(systemName: "chevron.down").font(.system(size: 9))
            }
            .foregroundStyle(AppTheme.Colors.textSecondary)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.xs)
            .background(Capsule(style: .continuous).fill(AppTheme.Colors.surface))
        }
    }

    // MARK: - 列表

    @ViewBuilder
    private var contentList: some View {
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
                    systemImage: "list.bullet.rectangle",
                    title: "没有匹配的标的",
                    description: "换个市场或搜索词试试"
                )
            } else {
                ForEach(viewModel.items) { item in
                    instrumentCell(item)
                }
                if viewModel.canLoadMore {
                    HStack {
                        Spacer()
                        SkeletonBlock(height: 10).frame(width: 120)
                        Spacer()
                    }
                }
            }
        }
    }

    private func instrumentCell(_ item: InstrumentInfo) -> some View {
        Button {
            Haptics.selection()
            appState.navigate(to: .instruments, route: .instrumentDetail(item.code))
        } label: {
            ADCard(padding: AppTheme.Spacing.md) {
                HStack(spacing: AppTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                        Text(item.displayName)
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .lineLimit(1)
                        Text(item.code)
                            .font(AppTheme.Typography.numericCallout)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                    }
                    Spacer(minLength: AppTheme.Spacing.sm)
                    VStack(alignment: .trailing, spacing: AppTheme.Spacing.xs) {
                        tagChip(item.marketLabel, color: AppTheme.Colors.accent, background: AppTheme.Colors.accentSoft)
                        if let category = item.category, !category.isEmpty {
                            Text(category)
                                .font(AppTheme.Typography.caption)
                                .foregroundStyle(AppTheme.Colors.textMuted)
                                .lineLimit(1)
                        }
                    }
                }
            }
        }
        .buttonStyle(.plain)
        .onAppear {
            if item.id == viewModel.items.last?.id {
                Task { await viewModel.loadMore() }
            }
        }
    }

    private func tagChip(_ title: String, color: Color, background: Color) -> some View {
        Text(title)
            .font(AppTheme.Typography.caption)
            .foregroundStyle(color)
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, AppTheme.Spacing.xxs)
            .background(Capsule(style: .continuous).fill(background))
    }

    private var skeleton: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            ForEach(0..<6, id: \.self) { _ in
                ADCard(padding: AppTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        SkeletonBlock(height: 16).frame(maxWidth: 220)
                        SkeletonBlock(height: 12).frame(width: 120)
                    }
                }
            }
        }
    }
}

#Preview {
    NavigationStack {
        InstrumentsView()
            .environment(AppState())
    }
}
