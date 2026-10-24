import Foundation

private var failures: [String] = []

private func expect(
    _ condition: @autoclosure () -> Bool,
    _ message: String,
    file: StaticString = #filePath,
    line: UInt = #line
) {
    if !condition() {
        failures.append("\(file):\(line): \(message)")
    }
}

private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
    try JSONDecoder().decode(T.self, from: Data(json.utf8))
}

private func decodeConverted<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(T.self, from: Data(json.utf8))
}

// UserDTO remains compatible with responses from backends without the new flag.
do {
    let legacy = try decode(UserDTO.self, #"{"username":"legacy","role":"user"}"#)
    expect(legacy.mustChangePassword == false, "missing must_change_password must default to false")

    let pending = try decode(
        UserDTO.self,
        #"{"username":"new","role":"user","must_change_password":true}"#
    )
    expect(pending.mustChangePassword, "must_change_password=true must be decoded")

    // /auth/me goes through APIClient's convertFromSnakeCase decoder, while login
    // currently uses AuthService's default decoder. Both paths must preserve the flag.
    let convertedPending = try decodeConverted(
        UserDTO.self,
        #"{"username":"new","role":"user","must_change_password":true}"#
    )
    expect(convertedPending.mustChangePassword, "snake-case conversion must not hide the required flag")
    let convertedLegacy = try decodeConverted(UserDTO.self, #"{"username":"legacy","role":"user"}"#)
    expect(!convertedLegacy.mustChangePassword, "converted legacy responses must default to false")

    let cleared = UserDTO(username: "new", role: "user", mustChangePassword: false)
    expect(!cleared.mustChangePassword, "successful changes must be able to clear the user flag")
} catch {
    failures.append("UserDTO decoding threw unexpectedly: \(error)")
}

// The change-password contract uses snake_case on the wire and returns both tokens.
do {
    let request = ChangePasswordRequest(oldPassword: "old-pass", newPassword: "NewPass12345")
    let object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: String]
    expect(object?["old_password"] == "old-pass", "old_password request key mismatch")
    expect(object?["new_password"] == "NewPass12345", "new_password request key mismatch")
    expect(object?["oldPassword"] == nil, "request must not contain camelCase oldPassword")

    let response = try decode(
        ChangePasswordResponse.self,
        #"{"detail":"密码修改成功","access_token":"new-access","refresh_token":"new-refresh"}"#
    )
    expect(response.detail == "密码修改成功", "change-password detail mismatch")
    expect(response.accessToken == "new-access", "new access token mismatch")
    expect(response.refreshToken == "new-refresh", "new refresh token mismatch")
} catch {
    failures.append("Change-password DTO check threw unexpectedly: \(error)")
}

// API error payloads retain the backend's human-readable detail.
let error = APIError.fromResponse(statusCode: 422, data: Data(#"{"detail":"旧密码不正确"}"#.utf8))
expect(error.localizedDescription == "旧密码不正确", "backend detail must be shown to the user")

let fallback = APIError.fromResponse(statusCode: 500, data: Data("not-json".utf8))
expect(fallback.localizedDescription == "服务器错误 (500)", "non-JSON errors need a status-code fallback")

// Password policy: 12...64 characters, at least one ASCII letter and one digit.
let valid12 = "Abcdef123456"
expect(valid12.count == 12, "test fixture must contain 12 characters")
expect(PasswordPolicy.validate(valid12) == nil, "a valid 12-character password was rejected")
let fiveFlags = String(repeating: "🇨🇳", count: 5) + "a1"
expect(fiveFlags.unicodeScalars.count == 12, "flag fixture must contain 12 Unicode scalars")
expect(
    PasswordPolicy.validate(fiveFlags) == nil,
    "iOS must count Unicode scalars like the backend, not extended grapheme clusters"
)
expect(PasswordPolicy.validate("") == "密码不能为空", "empty password must be rejected")
expect(PasswordPolicy.validate("Abc123") != nil, "password shorter than 12 characters must be rejected")
expect(PasswordPolicy.validate("Abcdefghijkl") != nil, "password without a digit must be rejected")
expect(PasswordPolicy.validate("123456789012") != nil, "password without a letter must be rejected")
expect(
    PasswordPolicy.validate(String(repeating: "密", count: 11) + "1") != nil,
    "non-ASCII letters must not satisfy the letter rule"
)
expect(PasswordPolicy.validate("Abcdef12345!") == nil, "symbols are allowed alongside ASCII letters and digits")

let valid64 = String(repeating: "a", count: 63) + "1"
expect(valid64.count == 64, "test fixture must contain 64 characters")
expect(PasswordPolicy.validate(valid64) == nil, "a valid 64-character password was rejected")
expect(PasswordPolicy.validate(valid64 + "2") != nil, "password longer than 64 characters must be rejected")

let over72Bytes = String(repeating: "密", count: 24) + "a1"
expect(over72Bytes.count == 26, "test fixture must contain 26 characters")
expect(PasswordPolicy.validate(over72Bytes) != nil, "passwords over bcrypt's 72-byte limit must be rejected")

expect(
    PasswordPolicy.validateChange(oldPassword: "", newPassword: valid12, confirmation: valid12) != nil,
    "change-password requires the old password"
)
expect(
    PasswordPolicy.validateChange(oldPassword: "old", newPassword: "Abc123", confirmation: "Abc123") != nil,
    "change-password validates the new password"
)
expect(
    PasswordPolicy.validateChange(oldPassword: "old", newPassword: valid12, confirmation: valid12 + "x") != nil,
    "change-password requires matching confirmation"
)
expect(
    PasswordPolicy.validateChange(oldPassword: "old", newPassword: valid12, confirmation: valid12) == nil,
    "valid change-password input must pass"
)

if failures.isEmpty {
    print("PASS: \(#filePath) authentication contract and password policy checks")
} else {
    for failure in failures {
        fputs("FAIL: \(failure)\n", stderr)
    }
    exit(1)
}
