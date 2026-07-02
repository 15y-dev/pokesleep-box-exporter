"""
Android端末のセットアップスクリプト

frida-server のダウンロードと端末へのインストールを自動化します。

Usage:
    python setup_android.py

前提条件:
    - Android端末がUSBデバッグ有効でPCに接続済み
    - Android端末がroot化済み
"""

import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ADB = r"D:\android\platform-tools\adb.exe"
FRIDA_VERSION = "17.15.3"  # frida-tools と同じバージョン


def run_adb(*args, check=True, capture=True):
    """adbコマンドを実行"""
    cmd = [ADB] + list(args)
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=check,
    )
    if capture and result.stdout.strip():
        for line in result.stdout.strip().split("\n")[:5]:
            print(f"    {line}")
        lines = result.stdout.strip().split("\n")
        if len(lines) > 5:
            print(f"    ... ({len(lines) - 5} more lines)")
    return result


def run_adb_su(shell_cmd: str, check=True):
    """adb shell su -c でコマンドを実行 (APatch対応)"""
    cmd = [ADB, "shell", f'su -c "{shell_cmd}"']
    print(f"  $ adb shell su -c '{shell_cmd}'")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
    )
    if result.stdout.strip():
        for line in result.stdout.strip().split("\n")[:3]:
            print(f"    {line}")
        lines = result.stdout.strip().split("\n")
        if len(lines) > 3:
            print(f"    ... ({len(lines) - 3} more lines)")
    return result


def check_device():
    """デバイスが接続されているか確認"""
    print("\n[1/3] デバイス接続確認...")
    result = run_adb("devices")
    lines = [l for l in result.stdout.strip().split("\n")[1:] if l.strip()]
    devices = [l.split("\t")[0] for l in lines if "device" in l]

    if not devices:
        print("  ❌ デバイスが見つかりません。USBデバッグを有効にして接続してください。")
        sys.exit(1)

    print(f"  ✅ 接続デバイス: {devices[0]}")
    return devices[0]


def check_root():
    """root権限があるか確認"""
    print("\n[2/3] root権限確認...")
    result = run_adb_su("id", check=False)
    if result.returncode != 0 or "uid=0" not in result.stdout:
        print("  ❌ root権限がありません。端末がroot化されているか確認してください。")
        print("  → APatch で com.android.shell にスーパーユーザー権限を付与してください")
        sys.exit(1)
    print("  ✅ root権限: OK")


def get_device_arch():
    """デバイスのCPUアーキテクチャを取得"""
    result = run_adb("shell", "getprop", "ro.product.cpu.abi")
    arch = result.stdout.strip()
    print(f"  📱 CPU: {arch}")

    arch_map = {
        "arm64-v8a": "arm64",
        "armeabi-v7a": "arm",
        "x86_64": "x86_64",
        "x86": "x86",
    }
    return arch_map.get(arch, arch)


def install_frida_server():
    """frida-server をダウンロードして端末にインストール"""
    print("\n[3/3] frida-server インストール...")

    arch = get_device_arch()
    frida_name = f"frida-server-{FRIDA_VERSION}-android-{arch}"
    frida_url = f"https://github.com/frida/frida/releases/download/{FRIDA_VERSION}/{frida_name}.xz"

    download_dir = Path(__file__).parent / "downloads"
    download_dir.mkdir(exist_ok=True)

    xz_path = download_dir / f"{frida_name}.xz"
    bin_path = download_dir / frida_name

    # ダウンロード
    if not bin_path.exists():
        if not xz_path.exists():
            print(f"  ⬇️  ダウンロード中: {frida_url}")
            urllib.request.urlretrieve(frida_url, xz_path)
            print(f"  ✅ ダウンロード完了: {xz_path}")

        # 解凍 (xz)
        print(f"  📦 解凍中...")
        import lzma
        with lzma.open(xz_path) as f_in:
            with open(bin_path, "wb") as f_out:
                f_out.write(f_in.read())
        print(f"  ✅ 解凍完了: {bin_path}")
    else:
        print(f"  ✅ 既にダウンロード済み: {bin_path}")

    # 端末に転送
    print(f"  📤 端末に転送中...")
    run_adb("push", str(bin_path), "/data/local/tmp/frida-server")
    run_adb_su("chmod 755 /data/local/tmp/frida-server")
    print("  ✅ frida-server インストール完了: /data/local/tmp/frida-server")


def print_next_steps():
    """次のステップを表示"""
    print("\n" + "=" * 60)
    print("  ✅ セットアップ完了！")
    print("=" * 60)
    print()
    print("📋 次のステップ:")
    print()
    print("1️⃣  frida-server を起動:")
    print(f'   {ADB} shell "su -c /data/local/tmp/frida-server &"')
    print()
    print("2️⃣  ポケモンスリープを起動してボックスを開く")
    print()
    print("3️⃣  ボックスデータを取得:")
    print(f"   python dump_pokemon_box.py")
    print()
    print("   → pokemon_box.csv が出力されます")
    print()
    print("=" * 60)


def main():
    print("=" * 60)
    print("  Pokemon Sleep - Android セットアップ")
    print("=" * 60)

    check_device()
    check_root()
    install_frida_server()
    print_next_steps()


if __name__ == "__main__":
    main()
