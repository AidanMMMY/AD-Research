import SwiftUI

/// 研究笔记：AI 研究笔记列表（类型 tag + 日期 + 情绪）。
///
/// 详情交互分平台：iOS 弹 sheet（对齐 web ResearchNotes 的 Modal），
/// macOS 在外层 NavigationStack 上 push（桌面端不盖模态，可回退）。
struct ResearchView: View {
    @State private var viewModel = ResearchViewModel()
    @State private var selectedNote: ResearchNote?

    var body: some View {
        content
            .background(AppTheme.Colors.background)
            .navigationTitle("研究笔记")
            .task {
                await viewModel.loadIfNeeded()
            }
            #if os(macOS)
            // macOS：push 进详情列的 NavigationStack（ResearchNote 为 Identifiable，
            // 用 item 目标注册，无需新增 AppRoute case）
            .navigationDestination(item: $selectedNote) { note in
                ResearchNoteDetailView(note: note)
            }
            .onReceive(NotificationCenter.default.publisher(for: .adRefreshRequested)) { _ in
                Task { await viewModel.load() }
            }
            #else
            .sheet(item: $selectedNote) { note in
                ResearchNoteDetailView(note: note)
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
            if viewModel.notes.isEmpty {
                ScrollView {
                    EmptyStateView(
                        systemImage: "book.closed",
                        title: "还没有研究笔记",
                        description: "在标的详情页生成 AI 研究笔记后，会汇总到这里"
                    )
                    .padding(AppTheme.Spacing.lg)
                }
                .refreshable { await viewModel.load() }
            } else {
                noteList
            }
        }
    }

    // MARK: - 列表

    private var noteList: some View {
        List {
            Section {
                ForEach(viewModel.notes) { note in
                    noteRow(note)
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                        .listRowInsets(EdgeInsets(
                            top: AppTheme.Spacing.xs,
                            leading: AppTheme.Spacing.lg,
                            bottom: AppTheme.Spacing.xs,
                            trailing: AppTheme.Spacing.lg
                        ))
                }
            } header: {
                filterBar
                    .textCase(nil)
            }
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .refreshable { await viewModel.load() }
    }

    /// 类型筛选条（横向 chip，「全部」+ 四种笔记类型）
    private var filterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: AppTheme.Spacing.sm) {
                filterChip(key: nil, label: "全部")
                ForEach(ResearchViewModel.noteTypeOptions, id: \.key) { option in
                    filterChip(key: option.key, label: option.label)
                }
            }
            .padding(.vertical, AppTheme.Spacing.xs)
        }
    }

    private func filterChip(key: String?, label: String) -> some View {
        let selected = viewModel.noteType == key
        return Button {
            Haptics.selection()
            viewModel.noteType = key
        } label: {
            Text(label)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(selected ? AppTheme.Colors.accent : AppTheme.Colors.textSecondary)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.xs)
                .background(
                    Capsule(style: .continuous)
                        .fill(selected ? AppTheme.Colors.accentSoft : AppTheme.Colors.surface)
                )
        }
        .buttonStyle(.plain)
        .animation(AppTheme.Motion.standard, value: selected)
    }

    // MARK: - 笔记卡片

    private func noteRow(_ note: ResearchNote) -> some View {
        Button {
            Haptics.selection()
            selectedNote = note
        } label: {
            ADCard(padding: AppTheme.Spacing.md) {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    // 元信息行：类型 tag · 日期 · 情绪
                    HStack(spacing: AppTheme.Spacing.sm) {
                        typeTag(note.noteType)
                        Text(DateFormatting.formatDate(note.generatedAt ?? note.createdAt))
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textMuted)
                        Spacer()
                        sentimentChip(note.sentiment)
                    }
                    // 标的
                    HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.sm) {
                        Text(note.displayName)
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                            .lineLimit(1)
                        Text(note.instrumentCode)
                            .font(AppTheme.Typography.caption.monospacedDigit())
                            .foregroundStyle(AppTheme.Colors.textMuted)
                    }
                    // 摘要（summary 优先，退化正文拍平）
                    let excerptText = excerpt(of: note)
                    if !excerptText.isEmpty {
                        Text(excerptText)
                            .font(AppTheme.Typography.caption)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                    }
                    // 置信度
                    if let confidence = note.confidence {
                        Text("置信度 \(confidence)%")
                            .font(AppTheme.Typography.caption.monospacedDigit())
                            .foregroundStyle(AppTheme.Colors.textMuted)
                    }
                }
            }
        }
        .buttonStyle(.plain)
    }

    private func typeTag(_ noteType: String) -> some View {
        Text(ResearchNoteLabels.noteTypeLabel(noteType))
            .font(AppTheme.Typography.caption)
            .foregroundStyle(AppTheme.Colors.accent)
            .padding(.horizontal, AppTheme.Spacing.sm)
            .padding(.vertical, AppTheme.Spacing.xxs)
            .background(Capsule(style: .continuous).fill(AppTheme.Colors.accentSoft))
    }

    @ViewBuilder
    private func sentimentChip(_ sentiment: String?) -> some View {
        if let label = ResearchNoteLabels.sentimentLabel(sentiment) {
            let color: Color = {
                switch sentiment {
                case "bullish": return AppTheme.Colors.rise
                case "bearish": return AppTheme.Colors.fall
                default: return AppTheme.Colors.textMuted
                }
            }()
            Text(label)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(color)
                .padding(.horizontal, AppTheme.Spacing.sm)
                .padding(.vertical, AppTheme.Spacing.xxs)
                .background(Capsule(style: .continuous).fill(color.opacity(0.10)))
        }
    }

    private func excerpt(of note: ResearchNote) -> String {
        if let summary = note.summary?.trimmingCharacters(in: .whitespacesAndNewlines),
           !summary.isEmpty {
            return summary
        }
        return MarkdownRenderer.plainText(fromMarkdown: note.content, maxLines: 2)
    }

    // MARK: - 骨架屏

    private var skeletonList: some View {
        List {
            ForEach(0..<4, id: \.self) { _ in
                ADCard(padding: AppTheme.Spacing.md) {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                        SkeletonBlock(height: 10).frame(width: 140)
                        SkeletonBlock(height: 16).frame(maxWidth: 220)
                        SkeletonBlock(height: 12)
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
        ResearchView()
    }
}
