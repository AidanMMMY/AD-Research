import Foundation

/// Markdown 渲染（原生 ``AttributedString(markdown:)``，禁止 WebView）。
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
