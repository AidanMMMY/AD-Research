import SwiftUI

/// ⌘K 全局搜索面板（macOS sheet 呈现；iOS 可复用为 push 页）。
///
/// 命中后跳转：标的 → 标的详情；资讯 → 资讯详情，随后关闭面板。
struct GlobalSearchView: View {
    @State private var viewModel = GlobalSearchViewModel()
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @FocusState private var queryFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            queryField
            Divider().opacity(0.6)
            results
        }
        .frame(minWidth: 520, idealWidth: 560, minHeight: 420)
        .background(AppTheme.Colors.background)
        .onAppear { queryFocused = true }
        // Esc 关闭（sheet 默认已支持，这里保证列表焦点下也可退出）
        .onExitCommand { dismiss() }
    }

    // MARK: - 查询框

    private var queryField: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "magnifyingglass")
                .font(AppTheme.Typography.callout)
                .foregroundStyle(AppTheme.Colors.textMuted)
            TextField("搜索标的代码 / 名称 / 资讯关键词…", text: Binding(
                get: { viewModel.query },
                set: { viewModel.query = $0 }
            ))
            .textFieldStyle(.plain)
            .font(AppTheme.Typography.body)
            .focused($queryFocused)
            if viewModel.state == .loading {
                ProgressView()
                    .controlSize(.small)
            } else if !viewModel.query.isEmpty {
                Button {
                    viewModel.query = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, AppTheme.Spacing.lg)
        .padding(.vertical, AppTheme.Spacing.md)
    }

    // MARK: - 结果区

    @ViewBuilder
    private var results: some View {
        let trimmed = viewModel.query.trimmingCharacters(in: .whitespaces)
        if trimmed.isEmpty {
            hintView(icon: "command", text: "输入关键词开始搜索\n⌘K 随时呼出，Esc 关闭")
        } else if case .failed(let message) = viewModel.state {
            hintView(icon: "exclamationmark.triangle", text: message)
        } else if viewModel.state == .loaded && !viewModel.hasResults {
            hintView(icon: "doc.text.magnifyingglass", text: "没有找到与「\(trimmed)」相关的结果")
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    if !viewModel.instruments.isEmpty {
                        sectionHeader("标的")
                        ForEach(viewModel.instruments) { item in
                            instrumentRow(item)
                        }
                    }
                    if !viewModel.news.isEmpty {
                        sectionHeader("资讯")
                        ForEach(viewModel.news) { article in
                            newsRow(article)
                        }
                    }
                }
                .padding(AppTheme.Spacing.md)
            }
        }
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(AppTheme.Typography.caption)
            .foregroundStyle(AppTheme.Colors.textMuted)
            .padding(.top, AppTheme.Spacing.xs)
    }

    private func instrumentRow(_ item: InstrumentInfo) -> some View {
        Button {
            dismiss()
            appState.navigate(to: .instruments, route: .instrumentDetail(item.code))
        } label: {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "chart.line.uptrend.xyaxis")
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.accent)
                    .frame(width: 22)
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                    Text(item.nameZh ?? item.name)
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineLimit(1)
                    Text("\(item.code) · \(item.market)")
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, AppTheme.Spacing.sm)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .adHoverRow()
    }

    private func newsRow(_ article: NewsArticle) -> some View {
        Button {
            dismiss()
            appState.navigate(to: .news, route: .newsDetail(article.id))
        } label: {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: "newspaper")
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.accent)
                    .frame(width: 22)
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                    Text(article.titleZh ?? article.title)
                        .font(AppTheme.Typography.callout)
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .lineLimit(2)
                    Text(article.source)
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
                Spacer()
            }
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, AppTheme.Spacing.sm)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .adHoverRow()
    }

    private func hintView(icon: String, text: String) -> some View {
        VStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: icon)
                .font(.system(size: 26))
                .foregroundStyle(AppTheme.Colors.textMuted)
            Text(text)
                .font(AppTheme.Typography.callout)
                .foregroundStyle(AppTheme.Colors.textSecondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
