import Foundation
import Security

/// Secure storage for JWT tokens using the iOS Keychain.
actor KeychainStore {
    static let shared = KeychainStore()

    private let service = "com.adresearch.ios"

    private enum Key: String {
        case accessToken = "access_token"
        case refreshToken = "refresh_token"
    }

    // MARK: - Access Token

    var accessToken: String? {
        get { read(.accessToken) }
        set { write(.accessToken, value: newValue) }
    }

    var refreshToken: String? {
        get { read(.refreshToken) }
        set { write(.refreshToken, value: newValue) }
    }

    func clear() {
        accessToken = nil
        refreshToken = nil
    }

    // MARK: - Private

    private func read(_ key: Key) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func write(_ key: Key, value: String?) {
        // Delete existing
        SecItemDelete([kSecClass: kSecClassGenericPassword,
                       kSecAttrService: service,
                       kSecAttrAccount: key.rawValue] as CFDictionary)

        guard let value, let data = value.data(using: .utf8) else { return }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key.rawValue,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        ]
        SecItemAdd(query as CFDictionary, nil)
    }
}
