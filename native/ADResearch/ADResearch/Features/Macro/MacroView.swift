import SwiftUI

/// 宏观（占位）。后续模块 agent 在此填充：
/// 分区指标（cn/us/eu/global）、指标时间序列图、陈旧度提示。
/// 模型已就绪：MacroLatestItem / GlobalIndexRealtimeItem。
struct MacroView: View {
    var body: some View {
        FeaturePlaceholderView(
            systemImage: "globe.asia.australia",
            title: "宏观",
            description: "全球宏观指标：利率、汇率、股指、大宗的分区快照与历史序列"
        )
    }
}

/// 宏观指标详情占位（路由：AppRoute.macroDetail(code)）
struct MacroDetailPlaceholderView: View {
    let code: String

    var body: some View {
        FeaturePlaceholderView(
            systemImage: "chart.line.flattrend.xyaxis",
            title: code,
            description: "指标历史序列（Swift Charts）将在宏观模块接入"
        )
        .navigationTitle(code)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }
}
