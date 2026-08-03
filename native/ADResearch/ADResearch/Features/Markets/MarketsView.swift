import SwiftUI

/// 行情（占位）。后续模块 agent 在此填充：
/// 全球指数（/macro/indices/global 已接入 Dashboard，可复用）、
/// 市场分区（A股/美股/加密）、Swift Charts 走势图。
struct MarketsView: View {
    var body: some View {
        FeaturePlaceholderView(
            systemImage: "chart.line.uptrend.xyaxis",
            title: "行情",
            description: "全球市场行情：指数速览、分区行情、标的搜索与实时走势"
        )
    }
}
