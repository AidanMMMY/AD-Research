import Foundation

// MARK: - Request DTOs

struct LoginRequest: Codable {
    let username: String
    let password: String
}

struct ChangePasswordRequest: Codable {
    let oldPassword: String
    let newPassword: String

    enum CodingKeys: String, CodingKey {
        case oldPassword = "old_password"
        case newPassword = "new_password"
    }
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

struct ChangePasswordResponse: Codable {
    let detail: String
    let accessToken: String
    let refreshToken: String

    enum CodingKeys: String, CodingKey {
        case detail
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
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
    let mustChangePassword: Bool

    enum CodingKeys: String, CodingKey {
        case username
        case role
        case mustChangePassword = "must_change_password"
    }
}

extension UserDTO {
    private enum ConvertedCodingKeys: String, CodingKey {
        case mustChangePassword
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let convertedContainer = try decoder.container(keyedBy: ConvertedCodingKeys.self)
        username = try container.decode(String.self, forKey: .username)
        role = try container.decode(String.self, forKey: .role)
        let rawFlag = try container.decodeIfPresent(Bool.self, forKey: .mustChangePassword)
        let convertedFlag = try convertedContainer.decodeIfPresent(Bool.self, forKey: .mustChangePassword)
        mustChangePassword = rawFlag ?? convertedFlag ?? false
    }
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
