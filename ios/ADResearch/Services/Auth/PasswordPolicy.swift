import Foundation

/// Mirrors the backend password policy for immediate client-side feedback.
enum PasswordPolicy {
    static func validate(_ password: String) -> String? {
        guard !password.isEmpty else { return "密码不能为空" }
        guard password.count >= 12 else { return "密码至少 12 位，且需包含英文字母和数字" }
        guard password.count <= 64 else { return "密码长度不能超过 64 个字符" }
        guard password.utf8.count <= 72 else { return "密码过长，UTF-8 编码后不能超过 72 字节" }

        let scalars = password.unicodeScalars
        let hasASCIILetter = scalars.contains {
            (65...90).contains($0.value) || (97...122).contains($0.value)
        }
        let hasASCIIDigit = scalars.contains { (48...57).contains($0.value) }
        guard hasASCIILetter, hasASCIIDigit else {
            return "密码至少 12 位，且需包含英文字母和数字"
        }
        return nil
    }

    static func validateChange(
        oldPassword: String,
        newPassword: String,
        confirmation: String
    ) -> String? {
        guard !oldPassword.isEmpty else { return "请输入旧密码" }
        if let message = validate(newPassword) { return message }
        guard newPassword == confirmation else { return "两次输入的新密码不一致" }
        return nil
    }
}
