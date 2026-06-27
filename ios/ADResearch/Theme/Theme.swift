import SwiftUI

// MARK: - Colors (aligned with Web theme.css)

extension Color {
    // Background layers
    static let bgBase = Color(hex: "#0a0a0a")
    static let bgElevated = Color(hex: "#111111")
    static let bgHover = Color(hex: "rgba(255,255,255,0.03)")
    static let bgInput = Color(hex: "rgba(255,255,255,0.02)")

    // Accent — Neon Cyan
    static let accent = Color(hex: "#22d3ee")
    static let accentDim = Color(hex: "rgba(34,211,238,0.08)")
    static let accentBorder = Color(hex: "rgba(34,211,238,0.25)")
    static let accentHover = Color(hex: "#67e8f9")

    // Text
    static let textPrimary = Color(hex: "#f5f5f5")
    static let textSecondary = Color(hex: "#aaaaaa")
    static let textTertiary = Color(hex: "#555555")
    static let textMuted = Color(hex: "#3a3a3a")

    // Market (A-share red-up green-down convention)
    static let colorRise = Color(hex: "#ef4444")
    static let colorFall = Color(hex: "#22c55e")

    // Score
    static let scoreExcellent = Color(hex: "#22c55e")
    static let scoreGood = Color(hex: "#84cc16")
    static let scoreAverage = Color(hex: "#eab308")
    static let scorePoor = Color(hex: "#f97316")
    static let scoreBad = Color(hex: "#ef4444")

    // Border
    static let borderDefault = Color(hex: "rgba(255,255,255,0.06)")
    static let borderHover = Color(hex: "rgba(255,255,255,0.12)")
}

// MARK: - Hex helper

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)

        let r, g, b, a: UInt64
        switch hex.count {
        case 6:
            (a, r, g, b) = (255, (int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        case 8:
            (a, r, g, b) = ((int >> 24) & 0xFF, (int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }

        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

// MARK: - Font aliases (matching Web CSS variables)

extension Font {
    static let textH1 = Font.system(size: 26, weight: .medium)
    static let textH2 = Font.system(size: 20, weight: .medium)
    static let textH3 = Font.system(size: 16, weight: .medium)
    static let textBody = Font.system(size: 13, weight: .regular)
    static let textSmall = Font.system(size: 11, weight: .regular)
    static let textLabel = Font.system(size: 10, weight: .medium)
    static let textDataLg = Font.system(size: 24, weight: .regular, design: .monospaced)
    static let textDataMd = Font.system(size: 16, weight: .medium, design: .monospaced)
}
