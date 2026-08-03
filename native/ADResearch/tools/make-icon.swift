// ADResearch macOS 应用图标生成器（CLT-only，无需 Xcode）
// 用法：xcrun swiftc -O make-icon.swift -o make-icon && ./make-icon <输出目录>
// 产出：AppIcon.iconset/（16~1024 全套 PNG）+ AppIcon-1024.png 预览
//
// 设计说明：Big Sur+ 规范 —— 1024×1024 全出血方形（系统自套 squircle 蒙版），
// 主图形居中于 ~824×824 安全区。设计语言对齐登录页 Logo：深蓝底 + 上升折线。
import AppKit
import Foundation

func hex(_ rgb: UInt32, _ alpha: CGFloat = 1.0) -> NSColor {
    NSColor(calibratedRed: CGFloat((rgb >> 16) & 0xFF) / 255,
            green: CGFloat((rgb >> 8) & 0xFF) / 255,
            blue: CGFloat(rgb & 0xFF) / 255, alpha: alpha)
}

func drawIcon(size: CGFloat) -> NSImage {
    NSImage(size: NSSize(width: size, height: size), flipped: false) { rect in
        let ctx = NSGraphicsContext.current!.cgContext
        let s = size / 1024.0  // 设计坐标系缩放因子

        // ---- 背景：深海军蓝纵向渐变（上亮下暗），中心微提亮
        let bgGrad = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(),
                                colors: [hex(0x21365E).cgColor,
                                         hex(0x16263F).cgColor,
                                         hex(0x0C1524).cgColor] as CFArray,
                                locations: [0, 0.55, 1])!
        ctx.drawLinearGradient(bgGrad,
                               start: CGPoint(x: size / 2, y: size),
                               end: CGPoint(x: size / 2, y: 0),
                               options: [])
        // 中心径向提亮（主图形背后的柔光，限制在图形区域不外溢）
        let haloGrad = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(),
                                  colors: [hex(0x4F8CFF, 0.14).cgColor,
                                           hex(0x4F8CFF, 0).cgColor] as CFArray,
                                  locations: [0, 1])!
        ctx.drawRadialGradient(haloGrad,
                               startCenter: CGPoint(x: size / 2, y: size * 0.56), startRadius: 0,
                               endCenter: CGPoint(x: size / 2, y: size * 0.56), endRadius: size * 0.42,
                               options: [.drawsBeforeStartLocation])

        // ---- 主图形：上升折线 + 箭头，单一连续路径
        // 1024 设计网格：x 从 250 到 790，y 从 380 到 690（居中偏上）
        let path = NSBezierPath()
        path.move(to: CGPoint(x: 250 * s, y: 380 * s))
        path.line(to: CGPoint(x: 420 * s, y: 520 * s))
        path.line(to: CGPoint(x: 545 * s, y: 425 * s))
        path.line(to: CGPoint(x: 705 * s, y: 625 * s))
        // 箭头（沿末段 45° 上扬方向）
        path.move(to: CGPoint(x: 620 * s, y: 660 * s))
        path.line(to: CGPoint(x: 790 * s, y: 690 * s))
        path.line(to: CGPoint(x: 660 * s, y: 585 * s))
        path.lineCapStyle = .round
        path.lineJoinStyle = .round
        path.lineWidth = 56 * s

        // 柔光底层（轻，不糊）
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: -6 * s), blur: 30 * s,
                      color: hex(0x3E7BFA, 0.55).cgColor)
        hex(0x4F8CFF).setStroke()
        path.stroke()
        ctx.restoreGState()

        // 主描边：亮蓝→冰蓝渐变
        ctx.saveGState()
        ctx.addPath(path.cgPath)
        ctx.replacePathWithStrokedPath()
        ctx.clip()
        let lineGrad = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(),
                                  colors: [hex(0x4E8DFC).cgColor,
                                           hex(0x7FB5FF).cgColor,
                                           hex(0xB9DCFF).cgColor] as CFArray,
                                  locations: [0, 0.7, 1])!
        ctx.drawLinearGradient(lineGrad,
                               start: CGPoint(x: 250 * s, y: 380 * s),
                               end: CGPoint(x: 790 * s, y: 690 * s),
                               options: [])
        ctx.restoreGState()

        return true
    }
}

func writePNG(_ image: NSImage, side: Int, to url: URL) throws {
    guard let tiff = image.tiffRepresentation,
          let rep = NSBitmapImageRep(data: tiff) else {
        throw NSError(domain: "icon", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: "bitmap rep failed"])
    }
    rep.size = NSSize(width: side, height: side)
    guard let png = rep.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "icon", code: 2,
                      userInfo: [NSLocalizedDescriptionKey: "png encode failed"])
    }
    try png.write(to: url)
}

// ---- 主流程：iconset 全套 + 1024 预览
let outDir = URL(fileURLWithPath: CommandLine.arguments.count > 1
                 ? CommandLine.arguments[1] : ".", isDirectory: true)
let iconset = outDir.appendingPathComponent("AppIcon.iconset", isDirectory: true)
try FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)

let specs: [(String, Int)] = [
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]
for (name, side) in specs {
    let img = drawIcon(size: CGFloat(side))
    try writePNG(img, side: side, to: iconset.appendingPathComponent(name))
}
let preview = drawIcon(size: 1024)
try writePNG(preview, side: 1024, to: outDir.appendingPathComponent("AppIcon-1024.png"))
print("iconset written to \(iconset.path)")
