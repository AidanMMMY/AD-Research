import SwiftUI

/// 标的库（占位）。后续模块 agent 在此填充：
/// 标的列表/搜索、分类筛选、评分榜、标的详情（K线 + 指标）。
struct InstrumentsView: View {
    var body: some View {
        FeaturePlaceholderView(
            systemImage: "list.bullet.rectangle",
            title: "标的",
            description: "全平台标的库：ETF/个股/指数搜索、分类筛选与评分透视"
        )
    }
}

/// 标的详情占位（路由：AppRoute.instrumentDetail(code)）
struct InstrumentDetailPlaceholderView: View {
    let code: String

    var body: some View {
        FeaturePlaceholderView(
            systemImage: "chart.xyaxis.line",
            title: code,
            description: "标的详情（走势/评分/资金流/关联资讯）将在标的模块接入"
        )
        .navigationTitle(code)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }
}
