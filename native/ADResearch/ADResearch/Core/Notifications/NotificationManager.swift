#if os(macOS)
import AppKit
import Foundation
import UserNotifications

/// 每日研报本地提醒（macOS）。
///
/// 平台 06:30（Asia/Shanghai）出报，本地通知 07:00 触发作为阅读提醒——
/// 不轮询服务端，通知内容恒为提醒文案；点击经 AppDelegate 导航到研报分区。
/// 开关持久化在 UserDefaults（``enabledKey``）。
@MainActor
final class NotificationManager: NSObject {
    static let shared = NotificationManager()

    static let enabledKey = "dailyDigestReminderEnabled"
    private static let notificationID = "daily-digest-reminder"

    /// 通知点击广播（RootView 监听后导航到研报分区）
    static let openDigestNotification = Notification.Name("adOpenDigestFromNotification")

    private(set) var authorizationDenied = false

    var isEnabled: Bool {
        get { UserDefaults.standard.bool(forKey: Self.enabledKey) }
        set {
            UserDefaults.standard.set(newValue, forKey: Self.enabledKey)
            Task { await apply() }
        }
    }

    private override init() {
        super.init()
    }

    /// 应用启动时调用：若已启用则确保调度存在（系统升级/重装后兜底）
    func restoreIfNeeded() async {
        if isEnabled { await apply() }
    }

    /// 按当前开关状态对齐系统调度
    func apply() async {
        let center = UNUserNotificationCenter.current()
        if isEnabled {
            do {
                let granted = try await center.requestAuthorization(options: [.alert, .sound])
                if granted {
                    authorizationDenied = false
                    schedule(center)
                } else {
                    authorizationDenied = true
                    UserDefaults.standard.set(false, forKey: Self.enabledKey)
                }
            } catch {
                authorizationDenied = true
            }
        } else {
            center.removePendingNotificationRequests(withIdentifiers: [Self.notificationID])
        }
    }

    private func schedule(_ center: UNUserNotificationCenter) {
        let content = UNMutableNotificationContent()
        content.title = "每日 AI 综合研报已出"
        content.body = "点击查看今日行情复盘与自选透视"
        content.sound = .default

        var components = DateComponents()
        components.hour = 7
        components.minute = 0
        let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: true)
        let request = UNNotificationRequest(
            identifier: Self.notificationID, content: content, trigger: trigger
        )
        center.add(request)
    }
}

/// NSApplicationDelegate 适配器：接通知点击 → 广播导航事件。
/// macOS 点击通知横幅会激活应用，这里把研报导航意图发出去。
final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {

    func applicationDidFinishLaunching(_ notification: Notification) {
        UNUserNotificationCenter.current().delegate = self
        Task { @MainActor in
            await NotificationManager.shared.restoreIfNeeded()
        }
    }

    /// 前台也展示横幅（App 开着到点了照样提醒）
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .sound]
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        guard response.notification.request.identifier == "daily-digest-reminder" else { return }
        await MainActor.run {
            NSApplication.shared.activate(ignoringOtherApps: true)
            NotificationCenter.default.post(
                name: NotificationManager.openDigestNotification, object: nil
            )
        }
    }
}
#endif
