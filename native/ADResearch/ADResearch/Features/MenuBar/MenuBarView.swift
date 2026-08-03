#if os(macOS)
import SwiftUI

/// 菜单栏行情 widget（macOS MenuBarExtra，.window 样式）。
///
/// - label 常驻：图标 + 标普涨跌幅（无数据只显图标）
/// - 点开：五大指数行 + 更新时间 + 打开主窗口 / 刷新 / 退出
/// - 数据：``MenuBarViewModel``（60s 后台轻刷，label 数字不陈旧）
struct MenuBarView: View {
    let viewModel: MenuBarViewModel
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider().opacity(0.6)
            tickerRows
            Divider().opacity(0.6)
            actions
        }
        .frame(width: 260)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private var header: some View {
        HStack {
            Text("AlloyResearch")
                .font(AppTheme.Typography.callout.weight(.semibold))
                .foregroundStyle(AppTheme.Colors.textPrimary)
            Spacer()
            if viewModel.isLoading {
                ProgressView().controlSize(.mini)
            } else if let updated = viewModel.lastUpdated {
                Text(updated, style: .time)
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
            }
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.xs)
    }

    private var tickerRows: some View {
        VStack(spacing: 0) {
            if viewModel.hasData {
                ForEach(viewModel.tickers) { ticker in
                    HStack {
                        Text(ticker.title)
                            .font(AppTheme.Typography.callout)
                            .foregroundStyle(AppTheme.Colors.textSecondary)
                        Spacer()
                        Text(ticker.value.map { String(format: "%.2f", $0) } ?? "—")
                            .font(AppTheme.Typography.numericCallout)
                            .foregroundStyle(AppTheme.Colors.textPrimary)
                        Text(ticker.changePct.map { String(format: "%@%.2f%%", $0 > 0 ? "+" : "", $0) } ?? "—")
                            .font(AppTheme.Typography.caption.monospacedDigit())
                            .foregroundStyle(AppTheme.Colors.changeColor(ticker.changePct))
                            .frame(width: 64, alignment: .trailing)
                    }
                    .padding(.horizontal, AppTheme.Spacing.md)
                    .padding(.vertical, AppTheme.Spacing.xs)
                }
            } else {
                Text("登录后查看实时行情")
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, AppTheme.Spacing.md)
            }
        }
    }

    private var actions: some View {
        VStack(spacing: 0) {
            actionButton("打开 AlloyResearch", systemImage: "macwindow") {
                NSApplication.shared.activate(ignoringOtherApps: true)
                openWindow(id: "main")
            }
            actionButton("刷新", systemImage: "arrow.clockwise") {
                Task { await viewModel.refresh() }
            }
            actionButton("退出", systemImage: "power") {
                NSApplication.shared.terminate(nil)
            }
        }
    }

    private func actionButton(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: AppTheme.Spacing.sm) {
                Image(systemName: systemImage)
                    .font(AppTheme.Typography.caption)
                    .foregroundStyle(AppTheme.Colors.textMuted)
                    .frame(width: 16)
                Text(title)
                    .font(AppTheme.Typography.callout)
                    .foregroundStyle(AppTheme.Colors.textPrimary)
                Spacer()
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.xs)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .adHoverRow(cornerRadius: 4)
    }
}

/// 菜单栏常驻 label：图标 + 标普涨跌幅（无数据只显图标）。
/// 刷新循环挂在这里——label 常驻渲染，content 是懒加载的，
/// 任务挂 content 上会导致首次点击前 label 数字不更新。
struct MenuBarLabel: View {
    let model: MenuBarViewModel

    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: "chart.line.uptrend.xyaxis")
            if let pct = model.headlineChangePct {
                Text(String(format: "%@%.2f%%", pct > 0 ? "+" : "", pct))
            }
        }
        .task {
            await model.startAutoRefresh()
        }
    }
}
#endif
