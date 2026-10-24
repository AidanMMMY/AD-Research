import Foundation
import SwiftUI

@MainActor
final class ChangePasswordViewModel: ObservableObject {
    @Published var oldPassword = ""
    @Published var newPassword = ""
    @Published var confirmPassword = ""
    @Published var isLoading = false
    @Published var errorMessage: String?

    var hasRequiredFields: Bool {
        !oldPassword.isEmpty && !newPassword.isEmpty && !confirmPassword.isEmpty
    }

    private var validationMessage: String? {
        PasswordPolicy.validateChange(
            oldPassword: oldPassword,
            newPassword: newPassword,
            confirmation: confirmPassword
        )
    }

    func changePassword() async {
        guard !isLoading else { return }
        guard validationMessage == nil else {
            errorMessage = validationMessage
            return
        }

        isLoading = true
        errorMessage = nil

        do {
            try await AuthManager.shared.changePassword(
                oldPassword: oldPassword,
                newPassword: newPassword
            )
        } catch let error as APIError {
            errorMessage = error.localizedDescription
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}
