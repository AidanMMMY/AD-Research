import SwiftUI

/// 组合（占位）。后续模块 agent 在此填充：
/// 自选标的、标的池、收益对比。
struct PortfolioView: View {
    var body: some View {
        FeaturePlaceholderView(
            systemImage: "briefcase",
            title: "组合",
            description: "我的组合：自选标的跟踪、标的池管理与收益对比"
        )
    }
}
