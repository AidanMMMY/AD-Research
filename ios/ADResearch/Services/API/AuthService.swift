import Foundation

/// Auth API calls — corresponds to web/src/api/auth.ts
final class AuthService {
    private let baseURL: String

    init(baseURL: String) {
        self.baseURL = baseURL
    }

    private var url: URL? {
        URL(string: baseURL)
    }

    func login(username: String, password: String) async throws -> LoginResponse {
        let body = LoginRequest(username: username, password: password)
        return try await post("/auth/login", body: body)
    }

    func refresh(refreshToken: String) async throws -> RefreshResponse {
        let body = RefreshRequest(refreshToken: refreshToken)
        return try await post("/auth/refresh", body: body)
    }

    func logout(accessToken: String) async throws -> VoidResponse {
        return try await post("/auth/logout")
    }

    func registerDevice(name: String, platform: String, pushToken: String?) async throws -> DeviceDTO {
        let body = RegisterDeviceRequest(deviceName: name, platform: platform, pushToken: pushToken)
        return try await post("/auth/devices", body: body)
    }

    func listDevices() async throws -> [DeviceDTO] {
        return try await get("/auth/devices")
    }

    func removeDevice(id: Int) async throws -> VoidResponse {
        return try await delete("/auth/devices/\(id)")
    }

    // MARK: - Helpers

    private func get<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: "\(baseURL)\(path)") else { throw APIError.invalidURL }
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        addAuthHeader(&req)
        return try await perform(req)
    }

    private func post<T: Decodable>(_ path: String, body: (some Encodable)? = nil) async throws -> T {
        guard let url = URL(string: "\(baseURL)\(path)") else { throw APIError.invalidURL }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        addAuthHeader(&req)
        if let body {
            req.httpBody = try JSONEncoder().encode(AnyEncodable2(body))
        }
        return try await perform(req)
    }

    private func delete<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: "\(baseURL)\(path)") else { throw APIError.invalidURL }
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        addAuthHeader(&req)
        return try await perform(req)
    }

    private func addAuthHeader(_ request: inout URLRequest) {
        Task {
            if let token = await AuthManager.shared.accessToken {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            }
        }
    }

    private func perform<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200...299).contains(http.statusCode) else { throw APIError.serverError(http.statusCode) }
        return try JSONDecoder().decode(snakeCaseAware(T.self), from: data)
    }
}

// MARK: - Helpers

private struct AnyEncodable2: Encodable {
    let value: Encodable
    init(_ value: Encodable) { self.value = value }
    func encode(to encoder: Encoder) throws { try value.encode(to: encoder) }
}

/// Empty response placeholder
struct VoidResponse: Decodable {}

/// Decode with snake_case support
private func snakeCaseAware<T: Decodable>(_ type: T.Type) -> T.Type { type }
