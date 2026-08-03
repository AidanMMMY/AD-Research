import SwiftUI

#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

/// 设计令牌（镜像 ``web/src/styles/theme.css`` 的语义色体系）。
///
/// - 涨跌色遵循中国习惯：红涨绿跌（web 默认主题同款；
///   web 另有美股习惯变体，原生端暂不做主题切换，后续可加）
/// - 全部颜色深浅色自适应，取值逐一对照 theme.css 的 light/dark 两套 token
/// - 层级原则：浅色模式用极浅投影，深色模式用明度分层（bg < elevated < surface）
enum AppTheme {

    // MARK: - 语义色（值对照 theme.css）

    enum Colors {
        /// --bg-base（页面底色）
        static let background = dynamic(light: 0xFAFBFC, dark: 0x0D1117)
        /// --bg-elevated（卡片层）
        static let elevated = dynamic(light: 0xF3F5F7, dark: 0x161B22)
        /// --bg-surface（浮层/按压层）
        static let surface = dynamic(light: 0xEDF0F3, dark: 0x1C2128)
        /// --text-primary
        static let textPrimary = dynamic(light: 0x0F1115, dark: 0xE6EDF3)
        /// --text-secondary
        static let textSecondary = dynamic(light: 0x5B6778, dark: 0xA0A0A0)
        /// --text-muted
        static let textMuted = dynamic(light: 0x6B7280, dark: 0x7B828E)
        /// --accent（品牌蓝；暗色去饱和）
        static let accent = dynamic(light: 0x2563EB, dark: 0x60A5FA)
        /// --accent-dim（accent 低透明度底）
        static let accentSoft = dynamic(light: 0x2563EB, lightOpacity: 0.08, dark: 0x60A5FA, darkOpacity: 0.12)
        /// --color-rise（涨，中国习惯红）
        static let rise = dynamic(light: 0xC0392B, dark: 0xFF8585)
        /// --color-rise-dim
        static let riseSoft = dynamic(light: 0xC0392B, lightOpacity: 0.08, dark: 0xFF8585, darkOpacity: 0.14)
        /// --color-fall（跌，中国习惯绿）
        static let fall = dynamic(light: 0x1B7A3C, dark: 0x7DCB99)
        /// --color-fall-dim
        static let fallSoft = dynamic(light: 0x1B7A3C, lightOpacity: 0.08, dark: 0x7DCB99, darkOpacity: 0.14)
        /// --color-warning
        static let warning = dynamic(light: 0x8B5A00, dark: 0xEAB308)
        /// --color-success（与涨跌绿刻意区分）
        static let success = dynamic(light: 0x2A6E3F, dark: 0x34D399)
        /// --color-error
        static let error = dynamic(light: 0xC0392B, dark: 0xF87171)
        /// --border-default（深色用 GitHub 系 hairline，与 bg 体系同源）
        static let border = dynamic(light: 0xE5E7EB, dark: 0x30363D)

        /// 涨跌幅语义色：nil → 次级文本；|v| < 0.0005（视同为 0，含精度噪声）→ 次级文本；
        /// >0 → 涨色；<0 → 跌色。修正点：旧实现把 0 判为涨色，平盘被染红。
        static func changeColor(_ value: Double?) -> Color {
            guard let value else { return textSecondary }
            if abs(value) < 0.0005 { return textSecondary }
            return value > 0 ? rise : fall
        }
    }

    // MARK: - 间距（4pt 网格；iOS 触屏密度宁松勿挤，macOS 指针端可紧凑）

    enum Spacing {
        static let xxs: CGFloat = 2
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 12
        static let lg: CGFloat = 16
        static let xl: CGFloat = 20
        static let xxl: CGFloat = 24
        static let section: CGFloat = 32

        /// macOS 紧凑档：桌面投资工具信息密度优先（原则修正——触屏端"宁松勿挤"，
        /// 指针端"宁挤勿松"：无触控目标约束，密度换一屏信息量）。iOS 不使用本组。
        enum Compact {
            /// 紧凑卡片内边距（默认 lg=16 → 12）
            static let cardPadding: CGFloat = 12
            /// 紧凑列表/瓦片行距（默认 md=12 → 8）
            static let row: CGFloat = 8
        }
    }

    // MARK: - 圆角（连续圆角）

    enum Radius {
        /// 卡片。macOS 窗口内容密度高，圆角收小（10）更利落；iOS 保持 14。
        static let card: CGFloat = {
            #if os(macOS)
            return 10
            #else
            return 14
            #endif
        }()
        /// 控件（按钮/输入框）
        static let control: CGFloat = 10
        /// 小元素（chip/badge）
        static let chip: CGFloat = 8
    }

    // MARK: - 字号（正文 16-17pt、行长宽松；动态类型随系统缩放）

    enum Typography {
        static let largeTitle = Font.largeTitle.weight(.bold)
        static let pageTitle = Font.title2.weight(.semibold)
        static let cardTitle = Font.headline
        static let body = Font.body
        static let callout = Font.callout
        static let caption = Font.caption
        static let footnote = Font.footnote
        /// 数字等宽（行情/评分数值统一用，避免跳动）
        static let numericBody = Font.body.monospacedDigit()
        static let numericCallout = Font.callout.monospacedDigit()
        /// 展示大数字（hero 价格/关键指标），34pt 半粗 + 等宽数字
        static let display = Font.system(size: 34, weight: .semibold).monospacedDigit()
        /// 展示中数字（次级 hero / 瓦片主值），28pt 同风格
        static let displaySmall = Font.system(size: 28, weight: .semibold).monospacedDigit()
        /// 区块三级标题（20pt 半粗，介于 pageTitle 与 cardTitle 之间）
        static let title3 = Font.system(size: 20, weight: .semibold)
    }

    // MARK: - 动画（统一弹性曲线，禁止生硬无动画切换）

    enum Motion {
        /// 默认状态切换
        static let standard = Animation.snappy(duration: 0.25)
        /// 卡片出现/内容更新
        static let content = Animation.spring(duration: 0.4, bounce: 0.15)
        /// 轻量淡入
        static let fade = Animation.easeOut(duration: 0.2)
    }

    // MARK: - 动态颜色构造

    private static func dynamic(light: UInt32, dark: UInt32) -> Color {
        dynamic(light: light, lightOpacity: 1, dark: dark, darkOpacity: 1)
    }

    private static func dynamic(
        light: UInt32,
        lightOpacity: Double,
        dark: UInt32,
        darkOpacity: Double
    ) -> Color {
        #if canImport(UIKit)
        return Color(UIColor { traits in
            let hex = traits.userInterfaceStyle == .dark ? dark : light
            let opacity = traits.userInterfaceStyle == .dark ? darkOpacity : lightOpacity
            return UIColor(hex: hex).withAlphaComponent(opacity)
        })
        #elseif canImport(AppKit)
        return Color(NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            let hex = isDark ? dark : light
            let opacity = isDark ? darkOpacity : lightOpacity
            return NSColor(hex: hex).withAlphaComponent(opacity)
        })
        #else
        return Color.primary
        #endif
    }
}

// MARK: - 平台色 hex 构造

#if canImport(UIKit)
extension UIColor {
    convenience init(hex: UInt32) {
        let red = CGFloat((hex >> 16) & 0xFF) / 255
        let green = CGFloat((hex >> 8) & 0xFF) / 255
        let blue = CGFloat(hex & 0xFF) / 255
        self.init(red: red, green: green, blue: blue, alpha: 1)
    }
}
#elseif canImport(AppKit)
extension NSColor {
    convenience init(hex: UInt32) {
        let red = CGFloat((hex >> 16) & 0xFF) / 255
        let green = CGFloat((hex >> 8) & 0xFF) / 255
        let blue = CGFloat(hex & 0xFF) / 255
        self.init(srgbRed: red, green: green, blue: blue, alpha: 1)
    }
}
#endif
