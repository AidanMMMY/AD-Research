import SwiftUI

@main
struct ADResearchApp: App {
    @StateObject private var authManager = AuthManager.shared

    var body: some Scene {
        WindowGroup {
            Group {
                if authManager.isAuthenticated {
                    // Placeholder — will be MainTabView
                    Text("Authenticated")
                        .foregroundColor(.textPrimary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background(Color.bgBase)
                } else {
                    LoginView()
                        .preferredColorScheme(.dark)
                }
            }
            .task {
                await authManager.restoreSession()
            }
        }
    }
}
