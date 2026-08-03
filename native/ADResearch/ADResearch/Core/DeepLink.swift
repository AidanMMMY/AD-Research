import Foundation

/// alloyresearch:// URL scheme 深链解析。
///
/// 支持路由：
/// - alloyresearch://instrument/{code}  → 标的详情（如 alloyresearch://instrument/510300.SH）
/// - alloyresearch://news/{id}          → 资讯详情
/// - alloyresearch://digest/{date}      → 研报详情（YYYY-MM-DD）
/// - alloyresearch://section/{name}     → 顶层分区（dashboard/news/markets/digest/instruments/…）
///
/// 注册位置：build-macos-clt.sh make_plist（CLT 包）+ ADResearch/Info.plist（Xcode 构建）。
enum DeepLink {

    /// 解析并导航；无法识别的 URL 静默忽略（返回 false 便于测试断言）
    @MainActor
    @discardableResult
    static func handle(_ url: URL, appState: AppState) -> Bool {
        guard url.scheme == "alloyresearch",
              let host = url.host?.lowercased() else { return false }
        let firstPath = url.pathComponents.first(where: { $0 != "/" })

        switch host {
        case "instrument":
            guard let code = firstPath, !code.isEmpty else { return false }
            appState.navigate(to: .instruments, route: .instrumentDetail(code))
            return true
        case "news":
            guard let raw = firstPath, let id = Int(raw) else { return false }
            appState.navigate(to: .news, route: .newsDetail(id))
            return true
        case "digest":
            guard let date = firstPath, !date.isEmpty else { return false }
            appState.navigate(to: .digest, route: .digestDetail(date))
            return true
        case "section":
            guard let raw = firstPath,
                  let section = AppSection(rawValue: raw.lowercased()) else { return false }
            appState.selectSection(section)
            return true
        default:
            return false
        }
    }
}
