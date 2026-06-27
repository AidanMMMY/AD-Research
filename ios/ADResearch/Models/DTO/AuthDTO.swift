import Foundation

// MARK: - Request DTOs

struct LoginRequest: Codable {
    let username: String
    let password: String
}

struct RefreshRequest: Codable {
    let refreshToken: String

    enum CodingKeys: String, CodingKey {
        case refreshToken = "refresh_token"
    }
}

struct RegisterDeviceRequest: Codable {
    let deviceName: String
    let platform: String
    let pushToken: String?

    enum CodingKeys: String, CodingKey {
        case deviceName = "device_name"
        case platform
        case pushToken = "push_token"
    }
}

// MARK: - Response DTOs

struct LoginResponse: Codable {
    let accessToken: String
    let refreshToken: String
    let tokenType: String
    let user: UserDTO

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
        case tokenType = "token_type"
        case user
    }
}

struct RefreshResponse: Codable {
    let accessToken: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
    }
}

struct UserDTO: Codable {
    let username: String
    let role: String
}

struct DeviceDTO: Codable, Identifiable {
    let id: Int
    let deviceName: String
    let platform: String
    let lastActiveAt: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case deviceName = "device_name"
        case platform
        case lastActiveAt = "last_active_at"
        case createdAt = "created_at"
    }
}
