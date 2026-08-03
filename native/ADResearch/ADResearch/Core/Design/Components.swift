import SwiftUI

// MARK: - 共享 UI 组件库
//
// 后续模块 agent 统一复用这里的组件，禁止各自重造卡片/空态/涨跌文本。

/// 卡片容器：surface 底 + 连续圆角 + hairline 描边；
/// 浅色模式极浅投影，深色模式用明度分层（无投影）。
struct ADCard<Content: View>: View {
    @Environment(\.colorScheme) private var colorScheme
    var padding: CGFloat = AppTheme.Spacing.lg
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                    .fill(AppTheme.Colors.elevated)
            )
            .overlay(
                RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                    .strokeBorder(AppTheme.Colors.border, lineWidth: 0.5)
            )
            .shadow(
                color: Color.black.opacity(colorScheme == .light ? 0.04 : 0),
                radius: 8,
                x: 0,
                y: 2
            )
    }
}

/// 卡片头部：标题 + 副标题 + 可选尾部操作（如「阅读全文 →」）
struct ADCardHeader<Trailing: View>: View {
    let title: String
    var subtitle: String? = nil
    var systemImage: String? = nil
    @ViewBuilder var trailing: Trailing

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                    .symbolRenderingMode(.hierarchical)
            }
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xxs) {
                Text(title)
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                if let subtitle {
                    Text(subtitle)
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.Colors.textMuted)
                }
            }
            Spacer(minLength: AppTheme.Spacing.sm)
            trailing
        }
    }
}

extension ADCardHeader where Trailing == EmptyView {
    init(title: String, subtitle: String? = nil, systemImage: String? = nil) {
        self.title = title
        self.subtitle = subtitle
        self.systemImage = systemImage
        self.trailing = EmptyView()
    }
}

/// 涨跌幅文本：红涨绿跌（中国习惯）+ 等宽数字 + 自动 +/- 号
struct ChangeText: View {
    let value: Double?
    var font: Font = AppTheme.Typography.numericCallout

    var body: some View {
        Text(NumberFormatting.percent(value))
            .font(font)
            .foregroundStyle(AppTheme.Colors.changeColor(value))
    }
}

/// 空态视图（图标 + 标题 + 描述 + 可选操作）
struct EmptyStateView: View {
    let systemImage: String
    let title: String
    var description: String? = nil

    var body: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: systemImage)
                .font(.system(size: 32))
                .foregroundStyle(AppTheme.Colors.textMuted)
                .symbolRenderingMode(.hierarchical)
            Text(title)
                .font(AppTheme.Typography.cardTitle)
                .foregroundStyle(AppTheme.Colors.textSecondary)
            if let description {
                Text(description)
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, AppTheme.Spacing.xxl)
    }
}

/// 加载错误态（附重试按钮）
struct LoadErrorView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            EmptyStateView(systemImage: "exclamationmark.triangle", title: message)
            Button("重试", action: retry)
                .buttonStyle(.bordered)
        }
    }
}

/// 骨架屏占位：加载态统一用 redacted 而非裸 spinner
struct SkeletonBlock: View {
    var height: CGFloat = 14
    var cornerRadius: CGFloat = AppTheme.Radius.chip

    var body: some View {
        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
            .fill(AppTheme.Colors.surface)
            .frame(height: height)
            .shimmering()
    }
}

/// 柔和呼吸动画（骨架屏用）
private struct ShimmerModifier: ViewModifier {
    @State private var isAnimating = false

    func body(content: Content) -> some View {
        content
            .opacity(isAnimating ? 0.45 : 1)
            .animation(
                .easeInOut(duration: 0.9).repeatForever(autoreverses: true),
                value: isAnimating
            )
            .onAppear { isAnimating = true }
    }
}

extension View {
    func shimmering() -> some View {
        modifier(ShimmerModifier())
    }
}

/// 占位模块统一外观（后续模块 agent 填充功能前的默认页）
struct FeaturePlaceholderView: View {
    let systemImage: String
    let title: String
    let description: String

    var body: some View {
        ScrollView {
            VStack(spacing: AppTheme.Spacing.lg) {
                Spacer(minLength: AppTheme.Spacing.section)
                Image(systemName: systemImage)
                    .font(.system(size: 56))
                    .foregroundStyle(AppTheme.Colors.accent)
                    .symbolRenderingMode(.hierarchical)
                Text(title)
                    .font(AppTheme.Typography.pageTitle)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Text(description)
                    .font(AppTheme.Typography.body)
                    .foregroundStyle(AppTheme.Colors.textSecondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, AppTheme.Spacing.section)
                Text("模块建设中，敬请期待")
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                    .padding(.horizontal, AppTheme.Spacing.lg)
                    .padding(.vertical, AppTheme.Spacing.xs)
                    .background(
                        Capsule(style: .continuous).fill(AppTheme.Colors.accentSoft)
                    )
                Spacer(minLength: AppTheme.Spacing.section)
            }
            .frame(maxWidth: .infinity)
        }
        .background(AppTheme.Colors.background)
    }
}
