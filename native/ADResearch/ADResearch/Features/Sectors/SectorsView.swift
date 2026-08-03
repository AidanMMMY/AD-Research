import SwiftUI

/// 板块（占位）。后续模块 agent 在此填充：
/// 申万行业轮动、相对强弱、板块热力图。
struct SectorsView: View {
    var body: some View {
        FeaturePlaceholderView(
            systemImage: "square.grid.2x2",
            title: "板块",
            description: "行业板块轮动：申万指数回报、相对强弱与资金流向"
        )
    }
}
