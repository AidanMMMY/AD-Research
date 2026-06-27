import Foundation
import SwiftUI

@MainActor
final class LoginViewModel: ObservableObject {
    @Published var username = ""
    @Published var password = ""
    @Published var isLoading = false
    @Published var errorMessage: String?

    var isValid: Bool {
        !username.trimmingCharacters(in: .whitespaces).isEmpty &&
        !password.isEmpty
    }

    func login() async {
        guard isValid else { return }
        isLoading = true
        errorMessage = nil

        do {
            try await AuthManager.shared.login(username: username, password: password)
        } catch let error as APIError {
            errorMessage = error.localizedDescription
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}
