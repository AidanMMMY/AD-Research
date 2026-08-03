import SwiftUI

/// 资讯流（占位）。后续模块 agent 在此填充：
/// 列表（GET /news，模型已就绪：NewsArticle/NewsListParams）、
/// 筛选（market/source/importance/event_category）、
/// swipeActions（收藏/稍后读）、文章详情（sheet 或 push）。
struct NewsView: View {
    var body: some View {
        FeaturePlaceholderView(
            systemImage: "newspaper",
            title: "资讯",
            description: "全市场新闻聚合：中文优先双语流、事件分类、重要性分级、情绪标注"
        )
    }
}

/// 资讯详情占位（路由：AppRoute.newsDetail(id)）
struct NewsDetailPlaceholderView: View {
    let articleID: Int

    var body: some View {
        FeaturePlaceholderView(
            systemImage: "doc.richtext",
            title: "资讯详情",
            description: "文章 #\(articleID) 的正文渲染（原生 Markdown）将在资讯模块接入"
        )
        .navigationTitle("资讯详情")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }
}
