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
}
