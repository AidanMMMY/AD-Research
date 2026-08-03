import Foundation

/// 一个 REST 请求的描述（路径 + 方法 + 查询参数 + 可选 JSON 请求体）。
///
/// 端点清单逐字段核对自 ``web/src/api/*.ts``（见 native/README.md 契约核对清单）。
/// 后续模块 agent 在此追加静态方法即可，不要改动既有端点。
struct Endpoint: Sendable {
    enum Method: String, Sendable {
        case get = "GET"
        case post = "POST"
        case put = "PUT"
        case delete = "DELETE"
    }

    var method: Method
    /// 以 ``/`` 开头的路径（相对于 ``AppConstants.apiBaseURL``）
    var path: String
    var queryItems: [URLQueryItem]
    /// 已编码好的 JSON 请求体
    var body: Data?
    /// 是否携带 Authorization 头（登录/刷新接口为 false）
    var requiresAuth: Bool
    /// 是否为刷新令牌调用（刷新自身 401 时不再进入刷新循环）
    var isRefreshCall: Bool

    init(
        method: Method,
        path: String,
        queryItems: [URLQueryItem] = [],
        body: Data? = nil,
        requiresAuth: Bool = true,
        isRefreshCall: Bool = false
    ) {
        self.method = method
        self.path = path
        self.queryItems = queryItems
        self.body = body
        self.requiresAuth = requiresAuth
        self.isRefreshCall = isRefreshCall
    }

    /// 便捷构造：JSON 请求体（encoder 已配置 ``.convertToSnakeCase``）
    static func json<Body: Encodable>(
        _ method: Method,
        path: String,
        body: Body,
        queryItems: [URLQueryItem] = [],
        requiresAuth: Bool = true,
        isRefreshCall: Bool = false
    ) throws -> Endpoint {
        let data: Data
        do {
            data = try JSONCoding.encoder.encode(body)
        } catch {
            throw APIError.encodingFailed(error.localizedDescription)
        }
        return Endpoint(
            method: method,
            path: path,
            queryItems: queryItems,
            body: data,
            requiresAuth: requiresAuth,
            isRefreshCall: isRefreshCall
        )
    }
}

// MARK: - 端点清单（与 web 契约对齐）

extension Endpoint {

    // MARK: 认证（web/src/api/auth.ts）

    /// POST /auth/login {username, password}
    static func authLogin(_ request: LoginRequest) throws -> Endpoint {
        try .json(.post, path: "/auth/login", body: request, requiresAuth: false)
    }

    /// POST /auth/refresh {refresh_token}
    static func authRefresh(_ request: RefreshRequest) throws -> Endpoint {
        try .json(.post, path: "/auth/refresh", body: request, requiresAuth: false, isRefreshCall: true)
    }

    /// POST /auth/logout
    static var authLogout: Endpoint {
        Endpoint(method: .post, path: "/auth/logout")
    }

    /// GET /auth/me
    static var authMe: Endpoint {
        Endpoint(method: .get, path: "/auth/me")
    }

    // MARK: 每日研报（web/src/api/digest.ts）

    /// GET /digest?page=&page_size=
    static func digestList(page: Int = 1, pageSize: Int = 20) -> Endpoint {
        Endpoint(
            method: .get,
            path: "/digest",
            queryItems: [
                URLQueryItem(name: "page", value: String(page)),
                URLQueryItem(name: "page_size", value: String(pageSize)),
            ]
        )
    }

    /// GET /digest/latest
    static var digestLatest: Endpoint {
        Endpoint(method: .get, path: "/digest/latest")
    }

    /// GET /digest/latest/summary（404 = 今日尚无报告 → 空态）
    static var digestLatestSummary: Endpoint {
        Endpoint(method: .get, path: "/digest/latest/summary")
    }

    /// GET /digest/by-date/{date}（date 为 YYYY-MM-DD，404 = 该日无报告）
    static func digestByDate(_ date: String) -> Endpoint {
        Endpoint(method: .get, path: "/digest/by-date/\(date)")
    }

    // MARK: 资讯（web/src/api/news.ts + web/src/types/news.ts）

    /// GET /news?...（参数对齐 NewsListParams；event_category 为重复查询参数）
    static func newsList(_ params: NewsListParams) -> Endpoint {
        var items: [URLQueryItem] = []
        func append(_ name: String, _ value: String?) {
            if let value, !value.isEmpty { items.append(URLQueryItem(name: name, value: value)) }
        }
        append("market", params.market)
        append("symbol", params.symbol)
        append("source", params.source)
        append("from_date", params.fromDate)
        append("to_date", params.toDate)
        append("q", params.q)
        if let page = params.page { append("page", String(page)) }
        if let pageSize = params.pageSize { append("page_size", String(pageSize)) }
        if let importanceMin = params.importanceMin { append("importance_min", String(importanceMin)) }
        // web 端 axios 序列化为 ?event_category=a&event_category=b，后端按重复参数解析
        for category in params.eventCategory ?? [] {
            items.append(URLQueryItem(name: "event_category", value: category))
        }
        return Endpoint(method: .get, path: "/news", queryItems: items)
    }

    /// GET /news/{id}
    static func newsDetail(_ id: Int) -> Endpoint {
        Endpoint(method: .get, path: "/news/\(id)")
    }

    /// POST /news/{id}/fetch-content（触发 Jina 抓取；恒不抛 5xx，错误收敛进响应体）
    static func newsFetchContent(_ id: Int) -> Endpoint {
        Endpoint(method: .post, path: "/news/\(id)/fetch-content")
    }

    /// POST /news/{id}/translate?target_language=zh（仅英文文章；命中缓存无 LLM 成本）
    static func newsTranslate(_ id: Int, targetLanguage: String = "zh") -> Endpoint {
        Endpoint(
            method: .post,
            path: "/news/\(id)/translate",
            queryItems: [URLQueryItem(name: "target_language", value: targetLanguage)]
        )
    }

    // MARK: 学习中心（web/src/api/learning.ts）

    /// GET /learning/feed?topic=&difficulty=&page=&page_size=&days=
    /// （importance 优先排序在服务端完成，客户端禁止重排）
    static func learningFeed(
        topic: String? = nil,
        difficulty: LearningDifficulty? = nil,
        page: Int = 1,
        pageSize: Int = 20,
        days: Int = 90
    ) -> Endpoint {
        var items: [URLQueryItem] = [
            URLQueryItem(name: "page", value: String(page)),
            URLQueryItem(name: "page_size", value: String(pageSize)),
            URLQueryItem(name: "days", value: String(days)),
        ]
        if let topic, !topic.isEmpty {
            items.append(URLQueryItem(name: "topic", value: topic))
        }
        if let difficulty {
            items.append(URLQueryItem(name: "difficulty", value: difficulty.rawValue))
        }
        return Endpoint(method: .get, path: "/learning/feed", queryItems: items)
    }

    /// GET /learning/topics（chip 条用的主题计数）
    static var learningTopics: Endpoint {
        Endpoint(method: .get, path: "/learning/topics")
    }

    /// POST /learning/articles/{id}/bookmark（收藏切换，响应为调用后真实状态）
    static func learningToggleBookmark(_ articleID: Int) -> Endpoint {
        Endpoint(method: .post, path: "/learning/articles/\(articleID)/bookmark")
    }

    /// POST /learning/articles/{id}/read（幂等，重复调用不刷新首次时间戳）
    static func learningMarkRead(_ articleID: Int) -> Endpoint {
        Endpoint(method: .post, path: "/learning/articles/\(articleID)/read")
    }

    /// GET /learning/bookmarks（我的收藏，bookmarked_at DESC）
    static func learningBookmarks(page: Int = 1, pageSize: Int = 20) -> Endpoint {
        Endpoint(
            method: .get,
            path: "/learning/bookmarks",
            queryItems: [
                URLQueryItem(name: "page", value: String(page)),
                URLQueryItem(name: "page_size", value: String(pageSize)),
            ]
        )
    }

    // MARK: 组合/自选（web/src/api/favorite.ts + pool.ts + market.ts）

    /// GET /favorites?limit=
    static func favoritesList(limit: Int = 200) -> Endpoint {
        Endpoint(
            method: .get,
            path: "/favorites",
            queryItems: [URLQueryItem(name: "limit", value: String(limit))]
        )
    }

    /// DELETE /favorites/{code}（移除自选）
    static func favoriteRemove(_ code: String) -> Endpoint {
        Endpoint(method: .delete, path: "/favorites/\(code)")
    }

    /// GET /pools（标的池列表，含成员）
    static var poolsList: Endpoint {
        Endpoint(method: .get, path: "/pools")
    }

    /// GET /market-data/snapshot?codes=a&codes=b（重复查询参数，对齐 web axios
    /// paramsSerializer indexes:null 的序列化）
    static func marketSnapshot(codes: [String]) -> Endpoint {
        Endpoint(
            method: .get,
            path: "/market-data/snapshot",
            queryItems: codes.map { URLQueryItem(name: "codes", value: $0) }
        )
    }

    // MARK: 研究笔记（web/src/api/research.ts）

    /// GET /research/notes?note_type=&limit=（响应为数组，无分页包装；
    /// AI 未配置时后端 503，消费方按错误态处理）
    static func researchNotes(noteType: String? = nil, limit: Int = 50) -> Endpoint {
        var items = [URLQueryItem(name: "limit", value: String(limit))]
        if let noteType, !noteType.isEmpty {
            items.append(URLQueryItem(name: "note_type", value: noteType))
        }
        return Endpoint(method: .get, path: "/research/notes", queryItems: items)
    }

    // MARK: 宏观（web/src/api/macro.ts）

    /// GET /macro/latest?region=
    static func macroLatest(region: String? = nil) -> Endpoint {
        var items: [URLQueryItem] = []
        if let region, !region.isEmpty {
            items.append(URLQueryItem(name: "region", value: region))
        }
        return Endpoint(method: .get, path: "/macro/latest", queryItems: items)
    }

    /// GET /macro/indices/global（实时全球指数快照，后端 200 保底、单项失败跳过）
    static var macroIndicesGlobal: Endpoint {
        Endpoint(method: .get, path: "/macro/indices/global")
    }

    /// GET /macro/indicators/{code}?start_date=&limit=（单指标历史序列）
    static func macroIndicatorSeries(code: String, startDate: String? = nil, limit: Int = 1500) -> Endpoint {
        var items = [URLQueryItem(name: "limit", value: String(limit))]
        if let startDate, !startDate.isEmpty {
            items.append(URLQueryItem(name: "start_date", value: startDate))
        }
        return Endpoint(
            method: .get,
            path: "/macro/indicators/\(code)",
            queryItems: items
        )
    }

    // MARK: 标的（web/src/api/instrument.ts）

    /// GET /etfs?market=&search=&page=&page_size=
    /// market 取值对齐 DB：A股 / US / HK / CRYPTO（nil = 全部）
    static func instrumentList(
        market: String? = nil,
        search: String? = nil,
        page: Int = 1,
        pageSize: Int = 20
    ) -> Endpoint {
        var items: [URLQueryItem] = [
            URLQueryItem(name: "page", value: String(page)),
            URLQueryItem(name: "page_size", value: String(pageSize)),
        ]
        if let market, !market.isEmpty {
            items.append(URLQueryItem(name: "market", value: market))
        }
        if let search, !search.isEmpty {
            items.append(URLQueryItem(name: "search", value: search))
        }
        return Endpoint(method: .get, path: "/etfs", queryItems: items)
    }

    /// GET /etfs/{code}
    static func instrumentDetail(_ code: String) -> Endpoint {
        Endpoint(method: .get, path: "/etfs/\(code)")
    }

    /// GET /etfs/{code}/sparkline?days=（days 上限 365，oldest → newest）
    static func instrumentSparkline(_ code: String, days: Int = 30) -> Endpoint {
        Endpoint(
            method: .get,
            path: "/etfs/\(code)/sparkline",
            queryItems: [URLQueryItem(name: "days", value: String(days))]
        )
    }

    /// GET /etfs/markets/list
    static var instrumentMarkets: Endpoint {
        Endpoint(method: .get, path: "/etfs/markets/list")
    }

    // MARK: 加密行情（web/src/api/crypto.ts）

    /// GET /crypto?search=&sort_by=&sort_order=&page=&page_size=
    static func cryptoList(
        search: String? = nil,
        sortBy: String = "name",
        sortOrder: String = "asc",
        page: Int = 1,
        pageSize: Int = 50
    ) -> Endpoint {
        var items: [URLQueryItem] = [
            URLQueryItem(name: "sort_by", value: sortBy),
            URLQueryItem(name: "sort_order", value: sortOrder),
            URLQueryItem(name: "page", value: String(page)),
            URLQueryItem(name: "page_size", value: String(pageSize)),
        ]
        if let search, !search.isEmpty {
            items.append(URLQueryItem(name: "search", value: search))
        }
        return Endpoint(method: .get, path: "/crypto", queryItems: items)
    }

    /// GET /crypto/{code}
    static func cryptoDetail(_ code: String) -> Endpoint {
        Endpoint(method: .get, path: "/crypto/\(code)")
    }

    // MARK: 板块轮动（web/src/api/sectorRotation.ts）

    /// GET /sector-rotation?trade_date=&window_weeks=&classification=
    /// classification：GICS（全球，默认）/ SW（申万2021一级，A股）
    static func sectorRotation(
        tradeDate: String? = nil,
        windowWeeks: Int = 4,
        classification: String = "GICS"
    ) -> Endpoint {
        var items: [URLQueryItem] = [
            URLQueryItem(name: "window_weeks", value: String(windowWeeks)),
            URLQueryItem(name: "classification", value: classification),
        ]
        if let tradeDate, !tradeDate.isEmpty {
            items.append(URLQueryItem(name: "trade_date", value: tradeDate))
        }
        return Endpoint(method: .get, path: "/sector-rotation", queryItems: items)
    }

    // MARK: 情绪（web/src/api/research.ts + app/api/v1/research.py）

    /// GET /research/sentiment-data/aggregate?market=&days=&limit=
    /// 注意 market 取值是 a_share / us / crypto / all（与资讯的 cn_a 不同）
    static func sentimentAggregate(
        market: String? = nil,
        days: Int = 14,
        limit: Int = 100
    ) -> Endpoint {
        var items: [URLQueryItem] = [
            URLQueryItem(name: "days", value: String(days)),
            URLQueryItem(name: "limit", value: String(limit)),
        ]
        if let market, !market.isEmpty, market != "all" {
            items.append(URLQueryItem(name: "market", value: market))
        }
        return Endpoint(method: .get, path: "/research/sentiment-data/aggregate", queryItems: items)
    }

    // MARK: 评分（app/api/v1/scoring.py + app/schemas/scoring.py ETFScoreResponse）

    /// GET /scores/{code} — 单标的最新评分（总分+分项+排名+区间收益）
    static func instrumentScore(_ code: String) -> Endpoint {
        Endpoint(method: .get, path: "/scores/\(code)")
    }

    /// GET /scores?template_id=&limit= — 评分榜（不传 template_id 用默认模板）
    static func scoresList(templateID: Int? = nil, limit: Int = 50) -> Endpoint {
        var items = [URLQueryItem(name: "limit", value: String(limit))]
        if let templateID {
            items.append(URLQueryItem(name: "template_id", value: String(templateID)))
        }
        return Endpoint(method: .get, path: "/scores", queryItems: items)
    }

    // MARK: 自选写操作（app/api/v1/favorites.py）

    /// POST /favorites/{code}/toggle — 切换自选（响应 FavoriteToggleResponse: is_favorite）
    static func favoriteToggle(_ code: String) -> Endpoint {
        Endpoint(method: .post, path: "/favorites/\(code)/toggle")
    }

    /// GET /favorites/{code}/status — 单标的自选状态（响应 FavoriteStatusResponse: is_favorite）
    static func favoriteStatus(_ code: String) -> Endpoint {
        Endpoint(method: .get, path: "/favorites/\(code)/status")
    }

    // MARK: 平台统计（app/api/v1/stats.py）

    /// GET /stats/overview — 平台 KPI 总览
    static var statsOverview: Endpoint {
        Endpoint(method: .get, path: "/stats/overview")
    }

    // MARK: 资金流（app/api/v1/fund_flow.py，2026-08-04 审计补齐）

    /// GET /fund-flow/market — 大盘资金流（响应 MarketFundFlowOut）
    static func fundFlowMarket(tradeDate: String? = nil) -> Endpoint {
        var items: [URLQueryItem] = []
        if let tradeDate, !tradeDate.isEmpty {
            items.append(URLQueryItem(name: "trade_date", value: tradeDate))
        }
        return Endpoint(method: .get, path: "/fund-flow/market", queryItems: items)
    }

    /// GET /fund-flow/sector — 板块资金流（响应 SectorFundFlowListResponse: items/total）
    static func fundFlowSector(tradeDate: String? = nil, limit: Int = 50) -> Endpoint {
        var items = [URLQueryItem(name: "limit", value: String(limit))]
        if let tradeDate, !tradeDate.isEmpty {
            items.append(URLQueryItem(name: "trade_date", value: tradeDate))
        }
        return Endpoint(method: .get, path: "/fund-flow/sector", queryItems: items)
    }

    /// GET /fund-flow/etf — ETF 资金流（响应 EtfFundFlowListResponse: items/total）
    static func fundFlowETF(tradeDate: String? = nil, limit: Int = 50) -> Endpoint {
        var items = [URLQueryItem(name: "limit", value: String(limit))]
        if let tradeDate, !tradeDate.isEmpty {
            items.append(URLQueryItem(name: "trade_date", value: tradeDate))
        }
        return Endpoint(method: .get, path: "/fund-flow/etf", queryItems: items)
    }

    /// GET /fund-flow/signals — 资金流信号（响应 FlowSignalListResponse: items/total）
    static func fundFlowSignals(limit: Int = 50) -> Endpoint {
        Endpoint(
            method: .get,
            path: "/fund-flow/signals",
            queryItems: [URLQueryItem(name: "limit", value: String(limit))]
        )
    }
}
