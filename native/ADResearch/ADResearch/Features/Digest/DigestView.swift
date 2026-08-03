import SwiftUI

/// 研报（占位）。后续模块 agent 在此填充：
/// 报告列表（GET /digest）、按日详情（GET /digest/by-date/{date}）、
/// 章节状态展示、原生 Markdown 正文渲染。
struct DigestView: View {
    var body: some View {
        FeaturePlaceholderView(
            systemImage: "doc.text.magnifyingglass",
            title: "研报",
            description: "AI 夜间综合研报：每日 6:30 发布，全球宏观 × 资金流 × 要闻综述"
        )
    }
}

/// 研报详情占位（路由：AppRoute.digestDetail(date)）
struct DigestDetailPlaceholderView: View {
    let reportDate: String

    var body: some View {
        FeaturePlaceholderView(
            systemImage: "doc.text.magnifyingglass",
            title: "研报详情",
            description: "\(reportDate) 的完整研报将在研报模块接入"
        )
        .navigationTitle("研报详情")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }
}
