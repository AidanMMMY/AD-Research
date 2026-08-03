import Foundation

/// 数字格式化（镜像 web Dashboard 的 formatTileValue / formatChange / formatSignedMoney）。
enum NumberFormatting {

    /// 涨跌幅：``+1.23%`` / ``-0.45%`` / ``—``（对齐 web formatChange）
    static func percent(_ value: Double?) -> String {
        guard let value, !value.isNaN else { return "—" }
        return String(format: "%@%.2f%%", value >= 0 ? "+" : "", value)
    }

    /// 不带符号的百分数（后端某些字段本身已是百分数语义）
    static func plainPercent(_ value: Double?) -> String {
        guard let value, !value.isNaN else { return "—" }
        return String(format: "%.2f%%", value)
    }

    /// 脉搏卡片数值（对齐 web formatTileValue）：
    /// unit 为 ``%`` 时直接拼百分号；绝对值 ≥1000 时千分位、否则两位小数。
    static func tileValue(_ value: Double?, unit: String = "") -> String {
        guard let value, !value.isNaN else { return "—" }
        if unit == "%" { return String(format: "%.2f%%", value) }
        if abs(value) >= 1000 {
            let formatter = NumberFormatter()
            formatter.numberStyle = .decimal
            formatter.maximumFractionDigits = 2
            return formatter.string(from: NSNumber(value: value)) ?? String(format: "%.2f", value)
        }
        return String(format: "%.2f", value)
    }

    /// 带符号金额（对齐 web formatSignedMoney）：``-1.23 亿`` / ``4567.89 万``
    static func signedMoney(_ value: Double?) -> String {
        guard let value, !value.isNaN else { return "—" }
        let absValue = abs(value)
        let sign = value < 0 ? "-" : ""
        if absValue >= 1e8 { return String(format: "%@%.2f 亿", sign, absValue / 1e8) }
        if absValue >= 1e4 { return String(format: "%@%.2f 万", sign, absValue / 1e4) }
        return String(format: "%@%.2f", sign, absValue)
    }

    /// 千分位整数（标的总数等 KPI 计数）
    static func count(_ value: Int) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        return formatter.string(from: NSNumber(value: value)) ?? "\(value)"
    }
}
