import SwiftUI

/// 登录页（2026-08-04 苹果质感重设计）。
///
/// 设计概念「终端晨光」：登录是进入终端前的过渡时刻——
/// 深海军蓝幕布上两团缓慢漂移的辉光，一条若隐若现的行情线，
/// 磨砂玻璃登录卡悬浮中央。动画遵循 Designing Fluid Interfaces：
/// - 入场用 spring 分幕（品牌先行、卡片随后），不用生硬的淡入
/// - 光晕漂移是可中断的 repeatForever autoreverse（无速度断点）
/// - 按钮按压即时反馈（pointer-down 缩放），错误用弹性抖动 + 触感
/// - accessibilityReduceMotion：漂移/描线全部降级为静态 + 淡入
struct LoginView: View {
    @Environment(AuthStore.self) private var authStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var username = ""
    @State private var password = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?

    /// 入场分幕状态
    @State private var brandShown = false
    @State private var cardShown = false
    /// 辉光漂移
    @State private var orbDrift = false
    /// 背景行情线描边进度
    @State private var lineTrim: CGFloat = 0
    /// 错误抖动触发计数（AnimatableModifier 驱动）
    @State private var shakes: CGFloat = 0

    @FocusState private var focusedField: Field?

    private enum Field { case username, password }

    private var canSubmit: Bool {
        !username.trimmingCharacters(in: .whitespaces).isEmpty && !password.isEmpty && !isSubmitting
    }

    var body: some View {
        ZStack {
            backdrop
            #if os(iOS)
            ScrollView {
                content
                    .padding(.horizontal, AppTheme.Spacing.xl)
                    .padding(.vertical, AppTheme.Spacing.section)
                    .frame(maxWidth: 480)
                    .frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
            #else
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            #endif
        }
        .preferredColorScheme(.dark)  // 登录幕布固定深色（过渡时刻的设计语言）
        .onAppear(perform: playEntrance)
    }

    // MARK: - 内容（品牌 + 卡片）

    private var content: some View {
        VStack(spacing: AppTheme.Spacing.section) {
            brandHeader
                .opacity(brandShown ? 1 : 0)
                .offset(y: brandShown ? 0 : 24)

            formCard
                .frame(width: 400)
                .opacity(cardShown ? 1 : 0)
                .offset(y: cardShown ? 0 : 28)
                .scaleEffect(cardShown ? 1 : 0.97)
        }
    }

    // MARK: - 幕布（渐变 + 辉光 + 行情线）

    private var backdrop: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.13, green: 0.21, blue: 0.37),
                    Color(red: 0.07, green: 0.12, blue: 0.22),
                    Color(red: 0.04, green: 0.08, blue: 0.15),
                ],
                startPoint: .top, endPoint: .bottom
            )

            // 辉光团：左上蓝 / 右下青，缓慢对冲漂移
            orb(color: Color(red: 0.31, green: 0.55, blue: 0.98), radius: 340)
                .offset(x: orbDrift ? -60 : 40, y: orbDrift ? -180 : -260)
                .offset(x: -160)
            orb(color: Color(red: 0.23, green: 0.72, blue: 0.86), radius: 300)
                .offset(x: orbDrift ? 80 : -30, y: orbDrift ? 220 : 140)
                .offset(x: 200)

            // 若隐若现的行情线：入场时自我描出，之后轻微呼吸
            BackdropTrendLine()
                .trim(from: 0, to: lineTrim)
                .stroke(
                    LinearGradient(
                        colors: [.white.opacity(0), .white.opacity(0.10), .white.opacity(0)],
                        startPoint: .leading, endPoint: .trailing
                    ),
                    style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round)
                )
                .padding(.horizontal, 40)

            // 顶部 hairline 受光
            LinearGradient(
                colors: [.white.opacity(0), .white.opacity(0.12), .white.opacity(0)],
                startPoint: .leading, endPoint: .trailing
            )
            .frame(height: 1)
            .frame(maxHeight: .infinity, alignment: .top)
        }
        .ignoresSafeArea()
    }

    private func orb(color: Color, radius: CGFloat) -> some View {
        Circle()
            .fill(
                RadialGradient(
                    colors: [color.opacity(0.35), color.opacity(0)],
                    center: .center, startRadius: 0, endRadius: radius / 2
                )
            )
            .frame(width: radius, height: radius)
            .blur(radius: 60)
    }

    // MARK: - 品牌区

    private var brandHeader: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            BrandGlyph()
                .stroke(
                    LinearGradient(
                        colors: [
                            Color(red: 0.31, green: 0.55, blue: 0.99),
                            Color(red: 0.50, green: 0.71, blue: 1.0),
                            Color(red: 0.73, green: 0.86, blue: 1.0),
                        ],
                        startPoint: .bottomLeading, endPoint: .topTrailing
                    ),
                    style: StrokeStyle(lineWidth: 5, lineCap: .round, lineJoin: .round)
                )
                .frame(width: 72, height: 72)
                .shadow(color: Color(red: 0.31, green: 0.55, blue: 0.98).opacity(0.45),
                        radius: 16, y: 4)

            VStack(spacing: AppTheme.Spacing.xs) {
                Text("AlloyResearch")
                    .font(.system(size: 34, weight: .bold))
                    .tracking(-0.5)
                    .foregroundStyle(.white)
                Text("投资研究平台 · 让每一次投资决策都有数据可依")
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(.white.opacity(0.65))
            }
        }
    }

    // MARK: - 登录卡（磨砂玻璃）

    private var formCard: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            Text("登录")
                .font(AppTheme.Typography.pageTitle)
                .foregroundStyle(.white)

            VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
                glassField(title: "用户名", field: .username) {
                    TextField("请输入用户名", text: $username)
                        .textContentType(.username)
                        #if os(iOS)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        #endif
                        .focused($focusedField, equals: .username)
                        .onSubmit { focusedField = .password }
                }
                glassField(title: "密码", field: .password) {
                    SecureField("请输入密码", text: $password)
                        .textContentType(.password)
                        .focused($focusedField, equals: .password)
                        .onSubmit { submit() }
                }
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(Color(red: 0.97, green: 0.44, blue: 0.44))
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }

            Button(action: submit) {
                Group {
                    if isSubmitting {
                        ProgressView()
                            .tint(.white)
                            .frame(maxWidth: .infinity)
                    } else {
                        Text("登 录")
                            .font(.headline)
                            .frame(maxWidth: .infinity)
                    }
                }
                .padding(.vertical, AppTheme.Spacing.sm)
            }
            .buttonStyle(PressableProminentStyle())
            .disabled(!canSubmit)
            .opacity(canSubmit ? 1 : 0.55)
            #if os(macOS)
            .keyboardShortcut(.defaultAction)
            #endif
        }
        .padding(AppTheme.Spacing.xxl)
        .background {
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .fill(.ultraThinMaterial)
                .opacity(0.72)
        }
        .overlay {
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .strokeBorder(
                    LinearGradient(
                        colors: [.white.opacity(0.22), .white.opacity(0.06)],
                        startPoint: .top, endPoint: .bottom
                    ),
                    lineWidth: 1
                )
        }
        .shadow(color: .black.opacity(0.35), radius: 40, y: 20)
        // 错误弹性抖动（reduceMotion 时关闭）
        .modifier(ShakeEffect(shakes: reduceMotion ? 0 : shakes))
    }

    private func glassField<Content: View>(
        title: String,
        field: Field,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
            Text(title)
                .font(AppTheme.Typography.caption)
                .foregroundStyle(.white.opacity(0.6))
            content()
                .textFieldStyle(.plain)
                .foregroundStyle(.white)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm + 2)
                .background {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .fill(.white.opacity(focusedField == field ? 0.10 : 0.06))
                }
                .overlay {
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .strokeBorder(
                            focusedField == field
                                ? Color(red: 0.38, green: 0.65, blue: 1.0).opacity(0.8)
                                : .white.opacity(0.12),
                            lineWidth: focusedField == field ? 1.5 : 1
                        )
                }
                .shadow(
                    color: Color(red: 0.38, green: 0.65, blue: 1.0)
                        .opacity(focusedField == field ? 0.25 : 0),
                    radius: 8
                )
                .animation(AppTheme.Motion.standard, value: focusedField)
        }
    }

    // MARK: - 入场编排

    private func playEntrance() {
        if reduceMotion {
            withAnimation(AppTheme.Motion.fade) {
                brandShown = true
                cardShown = true
            }
            lineTrim = 1
            return
        }
        // 品牌先行（spring response 0.5），卡片 0.15s 后跟上
        withAnimation(.spring(response: 0.55, dampingFraction: 0.86)) {
            brandShown = true
        }
        withAnimation(.spring(response: 0.6, dampingFraction: 0.88).delay(0.15)) {
            cardShown = true
        }
        withAnimation(.easeOut(duration: 1.6).delay(0.3)) {
            lineTrim = 1
        }
        // 辉光无限对冲漂移（autoreverse 无速度断点）
        withAnimation(.easeInOut(duration: 9).repeatForever(autoreverses: true)) {
            orbDrift = true
        }
    }

    // MARK: - 提交

    private func submit() {
        guard canSubmit else { return }
        isSubmitting = true
        errorMessage = nil
        Haptics.selection()
        Task {
            do {
                _ = try await authStore.login(
                    username: username.trimmingCharacters(in: .whitespaces),
                    password: password
                )
                Haptics.notify(success: true)
            } catch let error as APIError {
                showError(error.userMessage)
            } catch {
                showError("登录失败，请稍后重试")
            }
            isSubmitting = false
        }
    }

    private func showError(_ message: String) {
        withAnimation(AppTheme.Motion.standard) {
            errorMessage = message
        }
        Haptics.notify(success: false)
        guard !reduceMotion else { return }
        // 重新触发抖动：归零再驱动，保证连续输错也能再抖
        shakes = 0
        withAnimation(.linear(duration: 0.5)) {
            shakes = 1
        }
    }
}

// MARK: - 品牌字形（与应用图标同源的上升折线 + 箭头）

/// 1024 设计网格（与 tools/make-icon.swift 同一套坐标，y 已翻转为 SwiftUI 坐标）。
private struct BrandGlyph: Shape {
    func path(in rect: CGRect) -> Path {
        let s = min(rect.width, rect.height) / 1024
        func pt(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: rect.minX + x * s, y: rect.minY + y * s)
        }
        var p = Path()
        p.move(to: pt(250, 644))
        p.addLine(to: pt(420, 504))
        p.addLine(to: pt(545, 599))
        p.addLine(to: pt(705, 399))
        p.move(to: pt(620, 364))
        p.addLine(to: pt(790, 334))
        p.addLine(to: pt(660, 439))
        return p
    }
}

// MARK: - 背景行情线（装饰）

private struct BackdropTrendLine: Shape {
    func path(in rect: CGRect) -> Path {
        let w = rect.width, h = rect.height
        var p = Path()
        let ys: [CGFloat] = [0.56, 0.50, 0.58, 0.44, 0.52, 0.38, 0.46, 0.30]
        p.move(to: CGPoint(x: 0, y: h * ys[0]))
        for i in 1..<ys.count {
            p.addLine(to: CGPoint(x: w * CGFloat(i) / CGFloat(ys.count - 1), y: h * ys[i]))
        }
        return p
    }
}

// MARK: - 按压反馈按钮样式（pointer-down 即时缩放）

private struct PressableProminentStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background {
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 0.23, green: 0.45, blue: 0.94),
                                Color(red: 0.31, green: 0.55, blue: 0.99),
                            ],
                            startPoint: .top, endPoint: .bottom
                        )
                    )
            }
            .foregroundStyle(.white)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .opacity(configuration.isPressed ? 0.9 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

// MARK: - 错误弹性抖动

private struct ShakeEffect: GeometryEffect {
    /// 0→1 驱动一轮完整抖动
    var shakes: CGFloat

    var animatableData: CGFloat {
        get { shakes }
        set { shakes = newValue }
    }

    func effectValue(size: CGSize) -> ProjectionTransform {
        // 3 次往复、幅度衰减的正弦位移
        let x = sin(shakes * .pi * 6) * 10 * (1 - shakes)
        return ProjectionTransform(CGAffineTransform(translationX: x, y: 0))
    }
}

#Preview {
    LoginView()
        .environment(AuthStore.shared)
}
