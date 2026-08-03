import SwiftUI

// MARK: - 共享 UI 组件库
//
// 后续模块 agent 统一复用这里的组件，禁止各自重造卡片/空态/涨跌文本。

/// 卡片容器：surface 底 + 连续圆角 + hairline 描边；
/// 浅色模式极浅投影，深色模式用明度分层（无投影）。
struct ADCard<Content: View>: View {
    @Environment(\.colorScheme) private var colorScheme
    var padding: CGFloat = AppTheme.Spacing.lg
    /// macOS 紧凑模式：内边距压到 Spacing.Compact.cardPadding（12）。
    /// 桌面投资工具密度宁挤勿松（指针端无触控目标约束），iOS 保持默认宽松。
    var compact: Bool = false
    @ViewBuilder var content: Content

    private var effectivePadding: CGFloat {
        compact ? AppTheme.Spacing.Compact.cardPadding : padding
    }

    var body: some View {
        content
            .padding(effectivePadding)
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

/// 柔和呼吸动画（骨架屏用）；
/// Reduce Motion 开启时退化为静态 0.8 透明度，不做无限动画。
private struct ShimmerModifier: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isAnimating = false

    func body(content: Content) -> some View {
        if reduceMotion {
            content.opacity(0.8)
        } else {
            content
                .opacity(isAnimating ? 0.6 : 1)
                .animation(
                    .easeInOut(duration: 0.9).repeatForever(autoreverses: true),
                    value: isAnimating
                )
                .onAppear { isAnimating = true }
        }
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

// MARK: - 交互组件（hover / pressed）

/// 可点卡片按钮样式：hover 提亮 + accent 描边，pressed 缩放 0.98。
///
/// - hover（macOS 指针）：背景 surface → elevated 提亮 + 描边 accent 20%
/// - pressed（双平台）：缩放 0.98，动画 easeOut 0.12s
/// - iOS 触控不触发 hover，仅保留 pressed 效果（onHover 在 iOS 17+ 指针下亦可生效，属加分项）
///
/// 用法：`Button { ... } label: { ... }.buttonStyle(ADCardButtonStyle())`
/// 或 `.buttonStyle(.adCard)`。
struct ADCardButtonStyle: ButtonStyle {
    var padding: CGFloat = AppTheme.Spacing.md
    var cornerRadius: CGFloat = AppTheme.Radius.card
    @State private var isHovering = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(isHovering ? AppTheme.Colors.elevated : AppTheme.Colors.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .strokeBorder(
                        isHovering ? AppTheme.Colors.accent.opacity(0.2) : AppTheme.Colors.border,
                        lineWidth: 0.5
                    )
            )
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.12), value: isHovering)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
            .onHover { isHovering = $0 }
    }
}

extension ButtonStyle where Self == ADCardButtonStyle {
    /// `.buttonStyle(.adCard)` 便捷入口
    static var adCard: ADCardButtonStyle { ADCardButtonStyle() }
}

/// 列表行 hover 高亮：圆角背景在指针悬停时浮现（macOS 主战场，iOS 触控无感编译兼容）。
///
/// 用法：`rowContent.adHoverRow()`；自定义圆角 `.adHoverRow(cornerRadius: AppTheme.Radius.control)`。
private struct ADHoverRowModifier: ViewModifier {
    var cornerRadius: CGFloat = AppTheme.Radius.chip
    @State private var isHovering = false

    func body(content: Content) -> some View {
        content
            .background(
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(isHovering ? AppTheme.Colors.surface : Color.clear)
            )
            .animation(.easeOut(duration: 0.12), value: isHovering)
            .onHover { isHovering = $0 }
    }
}

extension View {
    /// 列表行 hover 圆角高亮（surface 底色，悬停浮现）
    func adHoverRow(cornerRadius: CGFloat = AppTheme.Radius.chip) -> some View {
        modifier(ADHoverRowModifier(cornerRadius: cornerRadius))
    }
}

// MARK: - 指标瓦片

/// 指标瓦片：名称 + 大数字值 + 涨跌 ChangeText，可选涨跌染色背景。
///
/// 统一 Dashboard 脉搏瓦片与 Macro 指数瓦片两套复制样式。
///
/// 用法：
/// ```swift
/// MetricTile(title: "上证指数", value: "3,245.67", change: 0.0123, tintedBackground: true)
/// ```
struct MetricTile: View {
    let title: String
    /// 已格式化的大数字值（调用方负责千分位/单位，字体为 Typography.displaySmall 等宽数字）
    let value: String
    /// 涨跌幅（0.0123 = +1.23%）；nil 时不渲染 ChangeText
    var change: Double? = nil
    /// 迷你染色背景：按涨跌染 rise/fall 6% 底；零值/nil 不染
    var tintedBackground: Bool = false
    var compact: Bool = false

    private var tintColor: Color? {
        guard tintedBackground, let change, abs(change) >= 0.0005 else { return nil }
        return change > 0 ? AppTheme.Colors.rise : AppTheme.Colors.fall
    }

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            Text(title)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(AppTheme.Colors.textMuted)
            Text(value)
                .font(AppTheme.Typography.displaySmall)
                .foregroundStyle(AppTheme.Colors.textPrimary)
            if let change {
                ChangeText(value: change)
            }
        }
        .padding(compact ? AppTheme.Spacing.Compact.cardPadding : AppTheme.Spacing.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                .fill(tintColor?.opacity(0.06) ?? AppTheme.Colors.elevated)
        )
        .overlay(
            RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                .strokeBorder(AppTheme.Colors.border, lineWidth: 0.5)
        )
    }
}
