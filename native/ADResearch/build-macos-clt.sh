#!/bin/bash
# AlloyResearch macOS 打包脚本（双模式）
#
# 模式 A（默认，CLT-only）：无 Xcode 许可也能跑——swiftc 直编 + 手工组装 .app
# 模式 B（Xcode）：先执行 sudo xcodebuild -license accept，再设 USE_XCODE=1 跑本脚本
#
# 用法：bash native/ADResearch/build-macos-clt.sh
# 产出：桌面 AlloyResearch-<version>-macOS-arm64.dmg
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$REPO_ROOT/native/ADResearch/ADResearch"
RES="$REPO_ROOT/native/ADResearch/Resources"
BUILD=/tmp/adresearch-build
APP_NAME="AlloyResearch"
BUNDLE_ID="net.alloyresearch.ADResearch"
VERSION="0.2.0"
DMG="$HOME/Desktop/${APP_NAME}-${VERSION}-macOS-arm64.dmg"

make_plist() {  # $1 = 输出路径
cat > "$1" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDevelopmentRegion</key><string>zh_CN</string>
	<key>CFBundleDisplayName</key><string>${APP_NAME}</string>
	<key>CFBundleExecutable</key><string>${APP_NAME}</string>
	<key>CFBundleIconFile</key><string>AppIcon</string>
	<key>CFBundleIdentifier</key><string>${BUNDLE_ID}</string>
	<key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
	<key>CFBundleName</key><string>${APP_NAME}</string>
	<key>CFBundlePackageType</key><string>APPL</string>
	<key>CFBundleShortVersionString</key><string>${VERSION}</string>
	<key>CFBundleVersion</key><string>1</string>
	<key>LSMinimumSystemVersion</key><string>14.0</string>
	<key>NSHighResolutionCapable</key><true/>
	<key>NSPrincipalClass</key><string>NSApplication</string>
</dict>
</plist>
EOF
}

if [ "${USE_XCODE:-0}" = "1" ]; then
  echo "==> Xcode 模式"
  cd "$REPO_ROOT/native/ADResearch"
  DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer xcodebuild \
    -project ADResearch.xcodeproj -scheme ADResearch -configuration Release \
    -destination 'platform=macOS' -derivedDataPath "$BUILD/dd" \
    CODE_SIGNING_ALLOWED=NO build | tail -3
  APP_PATH="$BUILD/dd/Build/Products/Release/${APP_NAME}.app"
  [ -d "$APP_PATH" ] || { echo "未找到 $APP_PATH"; exit 1; }
else
  echo "==> 1/4 复制源码并剥除 #Preview 块"
  python3 - "$SRC" "$BUILD/src" <<'EOF'
import pathlib, re, shutil, sys
src_root, dst_root = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
if dst_root.exists(): shutil.rmtree(dst_root)
stripped = 0
for f in sorted(src_root.rglob("*.swift")):
    lines = f.read_text().splitlines(keepends=True)
    out, i, n = [], 0, len(lines)
    while i < n:
        if re.match(r'^#Preview\b', lines[i]):
            depth = lines[i].count('{') - lines[i].count('}')
            i += 1
            while i < n and depth > 0:
                depth += lines[i].count('{') - lines[i].count('}')
                i += 1
            stripped += 1
            continue
        out.append(lines[i]); i += 1
    rel = f.relative_to(src_root)
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(''.join(out))
print(f"    stripped {stripped} #Preview blocks")
EOF

  echo "==> 2/4 swiftc 编译（arm64 macOS 14+）"
  cd "$BUILD/src"
  find . -name "*.swift" | sort > "$BUILD/sources.txt"
  xcrun swiftc -sdk /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk \
    -target arm64-apple-macos14.0 -O -whole-module-optimization \
    -framework SwiftUI -framework AppKit -framework Foundation \
    -framework Charts -framework Security \
    -emit-executable -o "$BUILD/$APP_NAME" @"$BUILD/sources.txt"

  echo "==> 3/4 组装 .app（含图标）+ ad-hoc 签名"
  APP_PATH="$BUILD/${APP_NAME}.app"
  rm -rf "$APP_PATH"
  mkdir -p "$APP_PATH/Contents/MacOS" "$APP_PATH/Contents/Resources"
  mv "$BUILD/$APP_NAME" "$APP_PATH/Contents/MacOS/"
  cp "$RES/AppIcon.icns" "$APP_PATH/Contents/Resources/"
  make_plist "$APP_PATH/Contents/Info.plist"
  codesign --force --sign - "$APP_PATH"
fi

echo "==> 4/4 打 DMG → $DMG"
hdiutil create -volname "$APP_NAME" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG" 2>/dev/null | tail -1
echo "DONE: $DMG"
