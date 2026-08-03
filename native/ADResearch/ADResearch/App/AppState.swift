import SwiftUI

/// 顶层导航分区（iOS Tab / macOS 侧栏共用同一份定义）。
///
/// 后续模块 agent 加新模块：在此追加 case + 标题/图标，
/// 再到 ``FeatureRouter.rootView(for:)`` 登记根视图即可。
enum AppSection: String, CaseIterable, Identifiable, Hashable, Sendable {
    // 主导航（iOS 五个 tab / macOS 侧栏第一组 + ⌘1-5）
    case dashboard
    case news
    case markets
    case digest
    case settings
    // 二级功能（macOS 侧栏第二组；iOS 通过导航路由进入）
    case instruments
    case macro
    case sentiment
    case sectors
    case fundFlow
    case portfolio
    case research
    case learning

    var id: String { rawValue }

    /// 五个主 tab
    static let primary: [AppSection] = [.dashboard, .news, .markets, .digest, .settings]

    /// 二级功能模块
    static let secondary: [AppSection] = allCases.filter { !primary.contains($0) }

    var title: String {
        switch self {
        case .dashboard: return "首页"
        case .news: return "资讯"
        case .markets: return "行情"
        case .digest: return "研报"
        case .settings: return "我的"
        case .instruments: return "标的"
        case .macro: return "宏观"
        case .sentiment: return "情绪"
        case .sectors: return "板块"
        case .fundFlow: return "资金流"
        case .portfolio: return "组合"
        case .research: return "研究笔记"
        case .learning: return "学习"
        }
    }

    var systemImage: String {
        switch self {
        case .dashboard: return "house"
        case .news: return "newspaper"
        case .markets: return "chart.line.uptrend.xyaxis"
        case .digest: return "doc.text.magnifyingglass"
        case .settings: return "person.circle"
        case .instruments: return "list.bullet.rectangle"
        case .macro: return "globe.asia.australia"
        case .sentiment: return "waveform.path.ecg"
        case .sectors: return "square.grid.2x2"
        case .fundFlow: return "arrow.left.arrow.right"
        case .portfolio: return "briefcase"
        case .research: return "book.closed"
        case .learning: return "graduationcap"
        }
    }
}

/// 模块内导航路由（NavigationStack 的 path 元素）。
///
/// 后续模块 agent 加详情页：追加 case + 在 ``FeatureRouter.destination(for:)``
/// 登记目标视图。所有 case 必须 ``Hashable``。
enum AppRoute: Hashable, Sendable {
    /// 资讯详情（文章 id）
    case newsDetail(Int)
    /// 研报详情（report_date，YYYY-MM-DD）
    case digestDetail(String)
    /// 标的详情（如 510300.SH）
    case instrumentDetail(String)
    /// 宏观指标详情（如 global_sp500）
    case macroDetail(String)
    /// 研究笔记详情（macOS 三栏布局详情列；iOS 仍走 sheet 不用此路由）
    case researchNote(ResearchNote)
    /// 进入某个二级功能模块（iOS 端从首页等入口 push）
    case section(AppSection)
}

/// 路由登记表：section → 根视图，route → 目标视图。
/// 这是后续 agent 唯一需要「登记」的地方，且只改本文件的 switch 分支。
enum FeatureRouter {

    @ViewBuilder
    static func rootView(for section: AppSection) -> some View {
        switch section {
        case .dashboard:
            DashboardView()
        case .news:
            NewsView()
        case .markets:
            MarketsView()
        case .digest:
            DigestView()
        case .settings:
            SettingsView()
        case .instruments:
            InstrumentsView()
        case .macro:
            MacroView()
        case .sentiment:
            SentimentView()
        case .sectors:
            SectorsView()
        case .fundFlow:
            FundFlowView()
        case .portfolio:
            PortfolioView()
        case .research:
            ResearchView()
        case .learning:
            LearningView()
        }
    }

    @ViewBuilder
    static func destination(for route: AppRoute) -> some View {
        switch route {
        case .newsDetail(let id):
            NewsDetailView(articleID: id)
        case .digestDetail(let date):
            DigestDetailView(reportDate: date)
        case .instrumentDetail(let code):
            InstrumentDetailView(code: code)
        case .macroDetail(let code):
            MacroDetailView(code: code)
        case .researchNote(let note):
            ResearchNoteDetailView(note: note)
        case .section(let section):
            rootView(for: section)
        }
    }
}

/// 全局应用状态（导航选择 + 各 tab 的 NavigationStack 路径）。
@Observable
final class AppState {
    /// 当前选中的顶层分区（iOS tab / macOS 侧栏共用）
    var selectedSection: AppSection = .dashboard

    /// ⌘K 全局搜索面板开关（macOS sheet；见 NavigationCommands / PlatformShell）
    var showGlobalSearch = false

    /// 快捷键速览弹窗开关（macOS 帮助菜单）
    var showShortcutsCheatSheet = false

    /// 各 tab 独立的 NavigationStack 路径（iOS）；macOS 用 detailPath
    var tabPaths: [AppSection: [AppRoute]] = [:]
    var detailPath: [AppRoute] = []

    func pathBinding(for section: AppSection) -> Binding<[AppRoute]> {
        Binding(
            get: { self.tabPaths[section] ?? [] },
            set: { self.tabPaths[section] = $0 }
        )
    }

    /// 仅切换顶层分区（不携带路由）。
    /// macOS 下切换时同步清空 detailPath，避免上一分区的详情栈残留串到新分区；
    /// iOS 各 tab 路径互相独立（tabPaths），无需处理。
    func selectSection(_ section: AppSection) {
        #if os(macOS)
        if section != selectedSection {
            detailPath.removeAll()
        }
        #endif
        selectedSection = section
    }

    /// 跳转到某分区并可选地携带一条路由（跨 tab 导航入口）
    func navigate(to section: AppSection, route: AppRoute? = nil) {
        withAnimation(AppTheme.Motion.standard) {
            selectSection(section)
        }
        if let route {
            #if os(macOS)
            // macOS 外壳（PlatformShell_macOS）详情列只绑定 detailPath：
            // 主导航分区的详情推送也必须写 detailPath，否则点击资讯/研报无任何反应。
            detailPath.append(route)
            #else
            if AppSection.primary.contains(section) {
                tabPaths[section, default: []].append(route)
            } else {
                detailPath.append(route)
            }
            #endif
        }
    }
}
