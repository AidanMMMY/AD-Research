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
    try JSONCoding.decoder.decode(T.self, from: Data(json.utf8))
}

// Both login and /auth/me use JSONCoding.convertFromSnakeCase.
do {
    let legacy = try decode(UserProfile.self, #"{"id":1,"username":"legacy","role":"user"}"#)
    expect(!legacy.mustChangePassword, "missing must_change_password must default to false")

    let pending = try decode(
        UserProfile.self,
        #"{"id":2,"username":"new","role":"user","must_change_password":true}"#
    )
    expect(pending.mustChangePassword, "must_change_password=true must survive response decoding")

    let login = try decode(
        LoginResponse.self,
        #"{"access_token":"a","refresh_token":"r","token_type":"bearer","user":{"id":2,"username":"new","role":"user","must_change_password":true}}"#
    )
    expect(login.user.mustChangePassword, "login must expose the mandatory password-change flag")
} catch {
    failures.append("User profile decoding threw unexpectedly: \(error)")
}

// Change-password request/response and endpoint contract.
do {
    let request = ChangePasswordRequest(oldPassword: "old-pass", newPassword: "NewPass12345")
    let object = try JSONSerialization.jsonObject(with: JSONCoding.encoder.encode(request)) as? [String: String]
    expect(object?["old_password"] == "old-pass", "old_password request key mismatch")
    expect(object?["new_password"] == "NewPass12345", "new_password request key mismatch")
    expect(object?["oldPassword"] == nil, "request must not contain camelCase oldPassword")

    let endpoint = try Endpoint.authChangePassword(request)
    expect(endpoint.path == "/auth/change-password", "change-password endpoint path mismatch")
    expect(endpoint.method == .post, "change-password must use POST")
    expect(endpoint.requiresAuth, "change-password must carry the current access token")

    let response = try decode(
        ChangePasswordResponse.self,
        #"{"detail":"密码修改成功","access_token":"new-access","refresh_token":"new-refresh"}"#
    )
    expect(response.detail == "密码修改成功", "change-password detail mismatch")
    expect(response.accessToken == "new-access", "new access token mismatch")
    expect(response.refreshToken == "new-refresh", "new refresh token mismatch")
} catch {
    failures.append("Change-password contract check threw unexpectedly: \(error)")
}

// Password policy: 12...64 characters, at least one ASCII letter and one digit.
let valid12 = "Abcdef123456"
expect(valid12.count == 12, "test fixture must contain 12 characters")
expect(PasswordPolicy.validate(valid12) == nil, "a valid 12-character password was rejected")
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
expect(PasswordPolicy.validate(over72Bytes) != nil, "passwords over bcrypt's 72-byte limit must be rejected")
expect(
    PasswordPolicy.validateChange(oldPassword: "", newPassword: valid12, confirmation: valid12) != nil,
    "change-password requires the old password"
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
    print("PASS: native authentication contract and password policy checks")
} else {
    for failure in failures {
        fputs("FAIL: \(failure)\n", stderr)
    }
    exit(1)
}
