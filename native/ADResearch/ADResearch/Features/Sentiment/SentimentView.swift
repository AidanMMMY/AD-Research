import SwiftUI

/// 情绪（占位）。后续模块 agent 在此填充：
/// 散户情绪聚合、多空比、争议度、主题权重。
struct SentimentView: View {
    var body: some View {
        FeaturePlaceholderView(
            systemImage: "waveform.path.ecg",
            title: "情绪",
            description: "市场情绪雷达：散户讨论聚合、多空比例与热门主题"
        )
    }
}
