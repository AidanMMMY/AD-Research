import SwiftUI

/// Markdown 渲染（原生解析 + SwiftUI 拼装，禁止 WebView）。
///
/// 两层 API：
/// - ``MarkdownRenderer.attributed(_:)``：行内级 AttributedString（保留给摘要卡等短文本）
/// - ``MarkdownBlockView``：块级渲染视图（标题/列表/引用/分隔线/代码块/表格），
///   供详情页正文直接嵌入 ScrollView
enum MarkdownRenderer {

    /// 解析为 AttributedString（行内语法保空白；解析失败退化为纯文本）
    static func attributed(_ markdown: String) -> AttributedString {
        var options = AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace
        )
        options.failurePolicy = .returnPartiallyParsedIfPossible
        if let result = try? AttributedString(markdown: markdown, options: options) {
            return result
        }
        return AttributedString(markdown)
    }

    /// 拍平成纯文本摘要（镜像 web ``DigestSummaryCard.summaryToPlainText``）：
    /// 逐行去 markdown 记号 → 取前 ``maxLines`` 行 → ``；`` 连接。
    static func plainText(fromMarkdown markdown: String?, maxLines: Int = 3) -> String {
        guard let markdown, !markdown.isEmpty else { return "" }
        return markdown
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                var text = String(line)
                text = stripPrefix(#/^\s{0,3}#{1,6}\s+/#, from: text) // 标题
                text = stripPrefix(#/^\s*[-*+]\s+/#, from: text) // 无序列表
                text = stripPrefix(#/^\s*\d+[.)、]\s+/#, from: text) // 有序列表
                text = stripPrefix(#/^\s*>\s?/#, from: text) // 引用
                text = text.replacingOccurrences(
                    of: #"[*_`~]"#,
                    with: "",
                    options: .regularExpression
                ) // 强调/代码记号
                return text.trimmingCharacters(in: .whitespaces)
            }
            .filter { !$0.isEmpty }
            .prefix(maxLines)
            .joined(separator: "；")
    }

    private static func stripPrefix(_ pattern: some RegexComponent, from text: String) -> String {
        if let match = text.firstMatch(of: pattern) {
            return String(text[match.range.upperBound...])
        }
        return text
    }
}

// MARK: - 块级模型

/// 解析后的 Markdown 块（行级切块，块内行内语法交给 AttributedString）
struct MarkdownBlock: Identifiable {
    struct ListItem: Identifiable {
        let id: Int
        /// 渲染用记号（无序：•/◦/▪ 按缩进阶梯；有序：原始编号 + "."）
        let marker: String
        /// 逻辑缩进层级（0 起）
        let depth: Int
        let text: String
    }

    enum Kind {
        case heading(level: Int, text: String)
        case paragraph(String)
        case list(items: [ListItem])
        case quote(lines: [String])
        case divider
        case code(language: String?, text: String)
        case table(header: [String], rows: [[String]])
    }

    let id: Int
    let kind: Kind
}

/// 行级块解析器：把 Markdown 文本切成 ``MarkdownBlock`` 序列。
///
/// 支持：ATX 标题（# ~ ######）、无序/有序列表（缩进嵌套）、引用、
/// 分隔线（--- / *** / ___）、围栏代码块（```）、管道表格（| ... |）、段落。
/// 不支持/未识别的行一律并入段落，保证任何输入都有可读输出。
enum MarkdownBlockParser {

    static func parse(_ markdown: String) -> [MarkdownBlock] {
        let lines = markdown
            .replacingOccurrences(of: "\r\n", with: "\n")
            .components(separatedBy: "\n")

        var blocks: [MarkdownBlock] = []
        var nextID = 0
        var paragraphLines: [String] = []

        func flushParagraph() {
            guard !paragraphLines.isEmpty else { return }
            let text = paragraphLines.joined(separator: "\n")
            paragraphLines.removeAll()
            blocks.append(MarkdownBlock(id: nextID, kind: .paragraph(text)))
            nextID += 1
        }

        func append(_ kind: MarkdownBlock.Kind) {
            blocks.append(MarkdownBlock(id: nextID, kind: kind))
            nextID += 1
        }

        var i = 0
        while i < lines.count {
            let raw = lines[i]
            let trimmed = raw.trimmingCharacters(in: .whitespaces)

            // 空行：段落分隔
            if trimmed.isEmpty {
                flushParagraph()
                i += 1
                continue
            }

            // 围栏代码块 ```lang ... ```
            if let fence = raw.firstMatch(of: #/^\s*```\s*([A-Za-z0-9_+-]*)\s*$/#) {
                flushParagraph()
                let language = fence.1.isEmpty ? nil : String(fence.1)
                var codeLines: [String] = []
                i += 1
                while i < lines.count,
                      lines[i].firstMatch(of: #/^\s*```\s*$/#) == nil {
                    codeLines.append(lines[i])
                    i += 1
                }
                i += 1 // 跳过闭合围栏（缺失时自然越界结束）
                append(.code(language: language, text: codeLines.joined(separator: "\n")))
                continue
            }

            // 表格：| 开头且至少 2 个管道的连续行块
            if trimmed.hasPrefix("|"), trimmed.filter({ $0 == "|" }).count >= 2 {
                flushParagraph()
                var tableLines: [String] = []
                while i < lines.count {
                    let row = lines[i].trimmingCharacters(in: .whitespaces)
                    guard row.hasPrefix("|"), row.filter({ $0 == "|" }).count >= 2 else { break }
                    tableLines.append(row)
                    i += 1
                }
                append(parseTable(tableLines))
                continue
            }

            // ATX 标题（允许闭合 # 序列）
            if let heading = raw.firstMatch(of: #/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/#),
               !heading.2.isEmpty {
                flushParagraph()
                append(.heading(level: heading.1.count, text: String(heading.2)))
                i += 1
                continue
            }

            // 分隔线（--- / *** / ___，可含空格；须先于列表判定）
            if raw.firstMatch(of: #/^\s{0,3}((-[ \t]*){3,}|(\*[ \t]*){3,}|(_[ \t]*){3,})$/#) != nil {
                flushParagraph()
                append(.divider)
                i += 1
                continue
            }

            // 引用块：连续 > 行
            if raw.firstMatch(of: #/^\s{0,3}>[ \t]?/#) != nil {
                flushParagraph()
                var quoteLines: [String] = []
                while i < lines.count,
                      let quote = lines[i].firstMatch(of: #/^\s{0,3}>[ \t]?(.*)$/#) {
                    quoteLines.append(String(quote.1))
                    i += 1
                }
                append(.quote(lines: quoteLines))
                continue
            }

            // 列表块：连续无序/有序项（允许混排，保留各自记号）
            if matchListItem(raw) != nil {
                flushParagraph()
                var items: [MarkdownBlock.ListItem] = []
                var itemID = 0
                while i < lines.count, let item = matchListItem(lines[i]) {
                    items.append(MarkdownBlock.ListItem(
                        id: itemID,
                        marker: item.marker,
                        depth: item.depth,
                        text: item.text
                    ))
                    itemID += 1
                    i += 1
                }
                append(.list(items: items))
                continue
            }

            // 普通段落行
            paragraphLines.append(raw)
            i += 1
        }
        flushParagraph()

        return blocks
    }

    // MARK: - 行级匹配

    private static func matchListItem(_ line: String) -> (marker: String, depth: Int, text: String)? {
        if let unordered = line.firstMatch(of: #/^(\s*)[-*+][ \t]+(.*)$/#) {
            let depth = indentDepth(of: unordered.1)
            let bullets = ["•", "◦", "▪"]
            return (bullets[min(depth, bullets.count - 1)], depth, String(unordered.2))
        }
        if let ordered = line.firstMatch(of: #/^(\s*)(\d{1,4})[.)][ \t]+(.*)$/#) {
            return ("\(ordered.2).", indentDepth(of: ordered.1), String(ordered.3))
        }
        return nil
    }

    private static func indentDepth(of whitespace: some StringProtocol) -> Int {
        var columns = 0
        for char in whitespace {
            columns += char == "\t" ? 4 : 1
        }
        return columns / 2
    }

    // MARK: - 表格

    private static func parseTable(_ lines: [String]) -> MarkdownBlock.Kind {
        var rows = lines.map(splitTableRow)
        guard !rows.isEmpty else { return .paragraph("") }

        let header = rows.removeFirst()
        // 丢弃分隔行（| --- | :---: | ... |）
        if let first = rows.first, isSeparatorRow(first) {
            rows.removeFirst()
        }
        // 列数对齐：以表头为准，不足补空、多余截断
        let columnCount = header.count
        let aligned = rows.map { row -> [String] in
            if row.count >= columnCount { return Array(row.prefix(columnCount)) }
            return row + Array(repeating: "", count: columnCount - row.count)
        }
        return .table(header: header, rows: aligned)
    }

    private static func splitTableRow(_ line: String) -> [String] {
        var row = line.trimmingCharacters(in: .whitespaces)
        if row.hasPrefix("|") { row.removeFirst() }
        if row.hasSuffix("|") { row.removeLast() }
        return row.components(separatedBy: "|").map {
            $0.trimmingCharacters(in: .whitespaces)
        }
    }

    private static func isSeparatorRow(_ cells: [String]) -> Bool {
        !cells.isEmpty && cells.allSatisfy {
            $0.firstMatch(of: #/^:?-{2,}:?$/#) != nil
        }
    }
}

// MARK: - 块级渲染视图

/// Markdown 块级正文视图：详情页长文直接嵌入 ScrollView。
///
/// 字号阶梯（AppTheme）：H1/H2 → title2 粗体、H3 → title3 半粗、H4+ → headline；
/// 正文 17pt（Font.body）+ 6pt 行距；表格/代码用等宽字体。深浅色全部走语义色。
struct MarkdownBlockView: View {
    let text: String

    init(text: String) {
        self.text = text
    }

    private var blocks: [MarkdownBlock] {
        MarkdownBlockParser.parse(text)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            ForEach(blocks) { block in
                blockView(block)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - 块分发

    @ViewBuilder
    private func blockView(_ block: MarkdownBlock) -> some View {
        switch block.kind {
        case .heading(let level, let text):
            headingView(level: level, text: text)
        case .paragraph(let text):
            Text(MarkdownRenderer.attributed(text))
                .font(AppTheme.Typography.body)
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .lineSpacing(6)
                .textSelection(.enabled)
        case .list(let items):
            listView(items)
        case .quote(let lines):
            quoteView(lines)
        case .divider:
            Divider()
                .overlay(AppTheme.Colors.border)
                .padding(.vertical, AppTheme.Spacing.xs)
        case .code(_, let text):
            codeView(text)
        case .table(let header, let rows):
            tableView(header: header, rows: rows)
        }
    }

    // MARK: - 标题

    private func headingView(level: Int, text: String) -> some View {
        let font: Font = {
            switch level {
            case ...2: return .title2.weight(.bold)
            case 3: return .title3.weight(.semibold)
            default: return .headline
            }
        }()
        return Text(MarkdownRenderer.attributed(text))
            .font(font)
            .foregroundStyle(AppTheme.Colors.textPrimary)
            .padding(.top, level <= 2 ? AppTheme.Spacing.sm : AppTheme.Spacing.xs)
            .textSelection(.enabled)
    }

    // MARK: - 列表

    private func listView(_ items: [MarkdownBlock.ListItem]) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            ForEach(items) { item in
                HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.sm) {
                    Text(item.marker)
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                    Text(MarkdownRenderer.attributed(item.text))
                        .foregroundStyle(AppTheme.Colors.textPrimary)
                        .textSelection(.enabled)
                }
                .padding(.leading, CGFloat(item.depth) * AppTheme.Spacing.md)
            }
        }
        .font(AppTheme.Typography.body)
        .lineSpacing(4)
    }

    // MARK: - 引用

    private func quoteView(_ lines: [String]) -> some View {
        HStack(alignment: .top, spacing: 0) {
            RoundedRectangle(cornerRadius: 1.5, style: .continuous)
                .fill(AppTheme.Colors.accent.opacity(0.55))
                .frame(width: 3)
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    Text(MarkdownRenderer.attributed(line))
                        .foregroundStyle(AppTheme.Colors.textSecondary)
                        .textSelection(.enabled)
                }
            }
            .font(AppTheme.Typography.body)
            .lineSpacing(4)
            .padding(.leading, AppTheme.Spacing.sm)
        }
        .padding(.vertical, AppTheme.Spacing.xxs)
    }

    // MARK: - 代码块

    private func codeView(_ text: String) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            Text(text)
                .font(AppTheme.Typography.callout.monospaced())
                .foregroundStyle(AppTheme.Colors.textPrimary)
                .lineSpacing(3)
                .textSelection(.enabled)
                .padding(AppTheme.Spacing.md)
        }
        .background(
            RoundedRectangle(cornerRadius: AppTheme.Radius.chip, style: .continuous)
                .fill(AppTheme.Colors.elevated)
        )
    }

    // MARK: - 表格

    private func tableView(header: [String], rows: [[String]]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            Grid(
                alignment: .leading,
                horizontalSpacing: AppTheme.Spacing.md,
                verticalSpacing: AppTheme.Spacing.xs
            ) {
                GridRow {
                    ForEach(Array(header.enumerated()), id: \.offset) { _, cell in
                        Text(MarkdownRenderer.attributed(cell))
                            .font(AppTheme.Typography.callout.monospacedDigit().weight(.semibold))
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                    }
                }
                Divider().overlay(AppTheme.Colors.border)
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    GridRow {
                        ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                            Text(MarkdownRenderer.attributed(cell))
                                .font(AppTheme.Typography.callout.monospacedDigit())
                                .foregroundStyle(AppTheme.Colors.textSecondary)
                        }
                    }
                }
            }
            .padding(AppTheme.Spacing.md)
        }
        .background(
            RoundedRectangle(cornerRadius: AppTheme.Radius.chip, style: .continuous)
                .fill(AppTheme.Colors.elevated)
        )
        .textSelection(.enabled)
    }
}
