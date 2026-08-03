#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import SwiftUI

// MARK: - 列表共用小组件（标的/组合/Markets 复用）

/// 迷你走势图（60×24，无坐标轴）：首尾定涨跌色（红涨绿跌）。
/// 可见行懒加载 ``Endpoint.instrumentSparkline`` 后传入 points。
struct MiniSparklineView: View {
    let points: [Double]

    var body: some View {
        let rising = (points.last ?? 0) >= (points.first ?? 0)
        let lineColor = points.count > 1
            ? (rising ? AppTheme.Colors.rise : AppTheme.Colors.fall)
            : AppTheme.Colors.textMuted

        Canvas { context, size in
            guard !points.isEmpty else { return }
            let minValue = points.min() ?? 0
            let maxValue = points.max() ?? 0
            var path = Path()
            if points.count < 2 || maxValue <= minValue {
                // 平盘/单点：中线一条直线
                let y = size.height / 2
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: size.width, y: y))
            } else {
                let stepX = size.width / CGFloat(points.count - 1)
                for (index, value) in points.enumerated() {
                    let x = CGFloat(index) * stepX
                    let ratio = (value - minValue) / (maxValue - minValue)
                    let y = size.height - CGFloat(ratio) * size.height
                    if index == 0 {
                        path.move(to: CGPoint(x: x, y: y))
                    } else {
                        path.addLine(to: CGPoint(x: x, y: y))
                    }
                }
            }
            context.stroke(path, with: .color(lineColor), lineWidth: 1.5)
        }
        .frame(width: 60, height: 24)
        .accessibilityHidden(true)
    }
}

/// 跨平台复制到剪贴板（macOS NSPasteboard / iOS UIPasteboard）
enum PasteboardCopy {
    static func copy(_ string: String) {
        #if canImport(AppKit)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(string, forType: .string)
        #elseif canImport(UIKit)
        UIPasteboard.general.string = string
        #endif
    }
}

// MARK: - 标的库

/// 标的库：全平台标的搜索 + 市场筛选 + 分页滚动加载 + 行情快照报价。
///
/// 搜索走 ``.searchable``（macOS 自动进 toolbar，白得 ⌘F），防抖保留
/// 300ms Task.sleep 模式。iOS：单列卡片流；macOS：紧凑行式（hairline 分隔，
/// 行高 ~44pt），排序控件进 toolbar。点击进 ``InstrumentDetailView``
/// （路由 AppRoute.instrumentDetail(code)）。
struct InstrumentsView: View {
    @Environment(AppState.self) private var appState
    @State private var viewModel = InstrumentsViewModel()
    @State private var searchText = ""
    @State private var searchTask: Task<Void, Never>?
    /// 自选切换结果提示（右键「切换自选」的反馈）
    @State private var favoriteNotice: String?

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
        .searchable(text: $searchText, prompt: "搜索代码 / 名称")
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
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                sortMenu
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .adRefreshRequested)) { _ in
            Task { await viewModel.reload() }
        }
        #endif
        .alert("自选", isPresented: noticePresented, presenting: favoriteNotice) { _ in
            Button("好的", role: .cancel) {}
        } message: { notice in
            Text(notice)
        }
    }

    private var noticePresented: Binding<Bool> {
        Binding(
            get: { favoriteNotice != nil },
            set: { if !$0 { favoriteNotice = nil } }
        )
    }

    // MARK: - 筛选条

    private var filterBar: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            marketMenu
            #if os(iOS)
            sortMenu
            #endif
            Spacer()
            if viewModel.total > 0 {
                Text("共 \(NumberFormatting.count(viewModel.total)) 只")
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
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

    /// 排序控件：macOS 进 toolbar（纯 Label），iOS 内联胶囊 Menu
    private var sortMenu: some View {
        Menu {
            ForEach(InstrumentsViewModel.SortOption.allCases) { option in
                Button {
                    Haptics.selection()
                    viewModel.sort = option
                } label: {
                    if viewModel.sort == option {
                        Label(option.label, systemImage: "checkmark")
                    } else {
                        Text(option.label)
                    }
                }
            }
        } label: {
            #if os(macOS)
            Label("排序", systemImage: "arrow.up.arrow.down")
            #else
            HStack(spacing: AppTheme.Spacing.xs) {
                Text(viewModel.sort.label).font(AppTheme.Typography.caption)
                Image(systemName: "arrow.up.arrow.down").font(.system(size: 9))
            }
            .foregroundStyle(AppTheme.Colors.textSecondary)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.xs)
            .background(Capsule(style: .continuous).fill(AppTheme.Colors.surface))
            #endif
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
                #if os(macOS)
                // macOS：行式紧凑列表（hairline 分隔，垂直 padding 减半）
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(viewModel.displayItems.enumerated()), id: \.element.id) { index, item in
                        instrumentRow(item)
                        if index < viewModel.displayItems.count - 1 {
                            Divider()
                        }
                    }
                }
                #else
                ForEach(viewModel.displayItems) { item in
                    instrumentCard(item)
                }
                #endif
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

    /// iOS 卡片行
    private func instrumentCard(_ item: InstrumentInfo) -> some View {
        Button {
            openDetail(item)
        } label: {
            ADCard(padding: AppTheme.Spacing.md) {
                instrumentRowContent(item)
            }
        }
        .buttonStyle(.plain)
        .contextMenu { instrumentContextMenu(item) }
        .onAppear { rowDidAppear(item) }
    }

    /// macOS 紧凑行（无卡片，行高约 44pt）
    private func instrumentRow(_ item: InstrumentInfo) -> some View {
        Button {
            openDetail(item)
        } label: {
            instrumentRowContent(item)
                .padding(.vertical, AppTheme.Spacing.xs)
                .padding(.horizontal, AppTheme.Spacing.xs)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .contextMenu { instrumentContextMenu(item) }
        .onAppear { rowDidAppear(item) }
    }

    /// 行内容（双端共用）：名称+代码 | sparkline | 现价+涨跌幅
    private func instrumentRowContent(_ item: InstrumentInfo) -> some View {
        let snapshot = viewModel.snapshots[item.code]
        return HStack(spacing: AppTheme.Spacing.md) {
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                Text(item.displayName)
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                    .lineLimit(1)
                HStack(spacing: AppTheme.Spacing.sm) {
                    Text(item.code)
                        .font(AppTheme.Typography.caption.monospacedDigit())
                        .foregroundStyle(AppTheme.Colors.textMuted)
                    tagChip(item.marketLabel, color: AppTheme.Colors.accent, background: AppTheme.Colors.accentSoft)
                    if let category = item.category, !category.isEmpty {
                        Text(category)
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textMuted)
                            .lineLimit(1)
                    }
                }
            }
            .layoutPriority(1)
            Spacer(minLength: AppTheme.Spacing.sm)
            // sparkline：固定位宽避免加载完成后布局跳动；未加载/无数据留空
            Group {
                if let points = viewModel.sparklines[item.code], points.count > 1 {
                    MiniSparklineView(points: points)
                }
            }
            .frame(width: 60, height: 24)
            quoteArea(snapshot: snapshot)
        }
    }

    /// 现价 + 涨跌幅；enrich 进行中渲染骨架
    private func quoteArea(snapshot: MarketSnapshotItem?) -> some View {
        VStack(alignment: .trailing, spacing: AppTheme.Spacing.xxs) {
            if snapshot == nil, viewModel.isEnriching {
                SkeletonBlock(height: 12).frame(width: 56)
                SkeletonBlock(height: 10).frame(width: 44)
            } else {
                Text(NumberFormatting.tileValue(snapshot?.close))
                    .font(AppTheme.Typography.numericCallout.weight(.medium))
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                ChangeText(value: snapshot?.changePct)
            }
        }
        .frame(minWidth: 72, alignment: .trailing)
    }

    @ViewBuilder
    private func instrumentContextMenu(_ item: InstrumentInfo) -> some View {
        Button {
            openDetail(item)
        } label: {
            Label("查看详情", systemImage: "arrow.right.circle")
        }
        Button {
            PasteboardCopy.copy(item.code)
        } label: {
            Label("复制代码", systemImage: "doc.on.doc")
        }
        Divider()
        Button {
            toggleFavorite(item.code)
        } label: {
            Label("切换自选", systemImage: "star")
        }
    }

    // MARK: - 动作

    private func openDetail(_ item: InstrumentInfo) {
        Haptics.selection()
        appState.navigate(to: .instruments, route: .instrumentDetail(item.code))
    }

    private func rowDidAppear(_ item: InstrumentInfo) {
        viewModel.loadSparklineIfNeeded(for: item.code)
        if item.id == viewModel.items.last?.id {
            Task { await viewModel.loadMore() }
        }
    }

    /// 加/撤自选（POST /favorites/{code}/toggle），结果用 alert 反馈
    private func toggleFavorite(_ code: String) {
        Task {
            do {
                let response: FavoriteToggleResponse = try await APIClient.shared.send(
                    .favoriteToggle(code)
                )
                favoriteNotice = response.isFavorite ? "已加入自选：\(code)" : "已移出自选：\(code)"
            } catch {
                favoriteNotice = "自选操作失败，请稍后重试"
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
                    HStack {
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                            SkeletonBlock(height: 16).frame(maxWidth: 220)
                            SkeletonBlock(height: 12).frame(width: 120)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: AppTheme.Spacing.sm) {
                            SkeletonBlock(height: 12).frame(width: 56)
                            SkeletonBlock(height: 10).frame(width: 44)
                        }
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
