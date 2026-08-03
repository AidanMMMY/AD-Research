import Foundation

/// 日期时间解析与格式化。
///
/// 后端时间字段混用三种形态：
/// - ``YYYY-MM-DD``（report_date / period）
/// - ISO8601 带毫秒（``2026-08-02T06:30:00.123Z`` 或带时区偏移）
/// - ISO8601 不带毫秒
/// DTO 层一律保留 String，这里统一解析。
enum DateFormatting {

    // MARK: - 解析

    private static let iso8601WithFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let iso8601: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private static let dateOnly: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()

    /// 宽松解析：ISO8601（带/不带毫秒）→ YYYY-MM-DD；失败返回 nil
    static func parse(_ string: String?) -> Date? {
        guard let string, !string.isEmpty else { return nil }
        if let date = iso8601WithFractional.date(from: string) { return date }
        if let date = iso8601.date(from: string) { return date }
        if let date = dateOnly.date(from: string) { return date }
        return nil
    }

    // MARK: - 相对时间（对齐 web utils/datetime 的 formatRelative 语义）

    /// 中文相对时间：刚刚 / N 分钟前 / N 小时前 / 昨天 / N 天前 / 超过 7 天落回日期时间
    static func relative(_ string: String?) -> String {
        guard let date = parse(string) else { return "—" }
        let interval = Date().timeIntervalSince(date)
        if interval < 0 { return formatDateTime(date) }
        if interval < 60 { return "刚刚" }
        if interval < 3600 { return "\(Int(interval / 60)) 分钟前" }
        if interval < 86400 { return "\(Int(interval / 3600)) 小时前" }
        if interval < 86400 * 2 { return "昨天" }
        if interval < 86400 * 7 { return "\(Int(interval / 86400)) 天前" }
        return formatDateTime(date)
    }

    // MARK: - 绝对时间

    private static let dateTimeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "M月d日 HH:mm"
        return formatter
    }()

    private static let dateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "yyyy年M月d日"
        return formatter
    }()

    /// ``8月2日 06:30``；解析失败返回 ``--``
    static func formatDateTime(_ date: Date) -> String {
        dateTimeFormatter.string(from: date)
    }

    /// ``2026年8月2日``；解析失败返回 ``--``
    static func formatDate(_ string: String?) -> String {
        guard let date = parse(string) else { return "—" }
        return dateFormatter.string(from: date)
    }

    /// 顶部状态条用：``8月2日 周六 06:30``
    static func nowWithWeekday() -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "zh_CN")
        formatter.dateFormat = "M月d日 E HH:mm"
        return formatter.string(from: Date())
    }
}
