import Foundation

#if os(iOS)
import UIKit

/// iOS 触觉反馈（轻量级，仅用于 selection changed 类场景）。
enum Haptics {
    /// 轻点选中型反馈（卡片点击、tab 切换、选项变更）
    static func selection() {
        let generator = UISelectionFeedbackGenerator()
        generator.prepare()
        generator.selectionChanged()
    }

    /// 操作成功/失败
    static func notify(success: Bool) {
        let generator = UINotificationFeedbackGenerator()
        generator.prepare()
        generator.notificationOccurred(success ? .success : .error)
    }
}
#else
/// macOS 无系统级轻量触觉 API，保留空调用以统一调用点。
enum Haptics {
    static func selection() {}
    static func notify(success: Bool) {}
}
#endif
