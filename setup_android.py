"""
Android端末のセットアップスクリプト

mitmproxy CA証明書のインストールと frida-server の配置を自動化します。

Usage:
    python setup_android.py

前提条件:
    - Android端末がUSBデバッグ有効でPCに接続済み
    - Android端末がroot化済み
    - mitmproxy が一度起動済み（CA証明書が生成されている）
"""

import hashlib
import os
import platform
import struct
import subprocess
import sys
import urllib.request
import zipfile
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
    # APatch では su -c の後のコマンド全体を引用符で囲む必要がある
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
    print("\n[1/5] デバイス接続確認...")
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
    print("\n[2/5] root権限確認...")
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


def _compute_cert_hash_python(cert_path: Path) -> str:
    """PEM証明書のsubject hashをPythonで計算（openssl互換）"""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        import hashlib as _hashlib

        with open(cert_path, "rb") as f:
            cert_data = f.read()

        cert = x509.load_pem_x509_certificate(cert_data)
        # Android uses subject_hash_old (MD5-based OpenSSL compat)
        subject_der = cert.subject.public_bytes()
        md5 = _hashlib.md5(subject_der).digest()
        # OpenSSL subject_hash_old = first 4 bytes of MD5 as little-endian uint32
        h = struct.unpack("<I", md5[:4])[0]
        return f"{h:08x}"
    except Exception as e:
        print(f"  ⚠️  Python証明書ハッシュ計算失敗: {e}")
        return "c8750f0d"  # mitmproxy CAの一般的なハッシュ


def install_ca_cert():
    """mitmproxy CA証明書をシステム証明書としてインストール (APatch/Magisk対応)"""
    print("\n[3/5] mitmproxy CA証明書インストール...")

    # mitmproxy CA証明書のパス
    home = Path.home()
    ca_cert = home / ".mitmproxy" / "mitmproxy-ca-cert.cer"
    ca_pem = home / ".mitmproxy" / "mitmproxy-ca-cert.pem"

    # PEM形式を優先（.cerと.pemは同じ内容の場合が多い）
    if ca_pem.exists():
        ca_cert = ca_pem
    elif not ca_cert.exists():
        print(f"  ⚠️  CA証明書が見つかりません: {ca_cert}")
        print("  → mitmproxy を一度起動して証明書を生成してください:")
        print(f"     {sys.executable} -m mitmproxy --listen-port 8080")
        print("     (起動したら Ctrl+C で終了してOK)")
        sys.exit(1)

    print(f"  📄 CA証明書: {ca_cert}")

    # 証明書ハッシュを計算
    cert_hash = _compute_cert_hash_python(ca_cert)
    cert_name = f"{cert_hash}.0"
    print(f"  📛 証明書名: {cert_name}")

    # APatch/Magisk モジュールとしてインストール
    # /data/adb/modules/ にモジュールを作成し、/system をオーバーレイする
    print("  📦 APatch/Magisk モジュールとして証明書をインストール...")

    module_id = "mitmproxy-cert"
    module_dir = f"/data/adb/modules/{module_id}"

    # 一時的に /sdcard に証明書を転送
    run_adb("push", str(ca_cert), "/sdcard/mitmproxy-ca-cert.pem")

    # モジュールディレクトリ作成
    run_adb_su(f"mkdir -p {module_dir}/system/etc/security/cacerts", check=False)

    # module.prop 作成
    module_prop = (
        f"id={module_id}\\n"
        f"name=mitmproxy CA Certificate\\n"
        f"version=1.0\\n"
        f"versionCode=1\\n"
        f"author=pokemonsleep-tools\\n"
        f"description=Install mitmproxy CA cert as system certificate"
    )
    run_adb_su(f"echo -e '{module_prop}' > {module_dir}/module.prop", check=False)

    # 証明書をモジュールにコピー
    run_adb_su(
        f"cp /sdcard/mitmproxy-ca-cert.pem {module_dir}/system/etc/security/cacerts/{cert_name}",
        check=False,
    )
    run_adb_su(
        f"chmod 644 {module_dir}/system/etc/security/cacerts/{cert_name}",
        check=False,
    )

    # 確認
    result = run_adb_su(
        f"ls -la {module_dir}/system/etc/security/cacerts/{cert_name}",
        check=False,
    )
    if result.returncode == 0 and cert_name in result.stdout:
        print(f"  ✅ CA証明書モジュール作成完了: {module_dir}")
        print(f"  ⚠️  反映には端末の再起動が必要です！")
    else:
        print("  ❌ モジュール作成に失敗しました")
        print()
        print("  → 代替方法: tmpfs overlay で即時反映")
        _install_ca_cert_tmpfs(cert_name)


def _install_ca_cert_tmpfs(cert_name: str):
    """tmpfs overlay を使って再起動なしでCA証明書をインストール"""
    print("  📦 tmpfs overlay で証明書をインストール...")

    cmds = [
        # 既存の証明書を tmpfs にコピー
        "mkdir -p /data/local/tmp/cacerts",
        "cp /system/etc/security/cacerts/* /data/local/tmp/cacerts/",
        # mitmproxy 証明書を追加
        f"cp /sdcard/mitmproxy-ca-cert.pem /data/local/tmp/cacerts/{cert_name}",
        f"chmod 644 /data/local/tmp/cacerts/{cert_name}",
        # tmpfs でマウント
        "mount -t tmpfs tmpfs /system/etc/security/cacerts",
        "cp /data/local/tmp/cacerts/* /system/etc/security/cacerts/",
        "chmod 644 /system/etc/security/cacerts/*",
        "chown root:root /system/etc/security/cacerts/*",
        # クリーンアップ
        "rm -rf /data/local/tmp/cacerts",
    ]

    for cmd in cmds:
        run_adb_su(cmd, check=False)

    # 確認
    result = run_adb_su(
        f"ls /system/etc/security/cacerts/{cert_name}",
        check=False,
    )
    if result.returncode == 0:
        print(f"  ✅ tmpfs overlay でCA証明書インストール完了（再起動不要！）")
        print(f"     ただし端末再起動で消えます。再起動後はモジュール版が有効になります。")
    else:
        print("  ❌ tmpfs overlay も失敗しました。")
        print("  → APatch アプリで com.android.shell にスーパーユーザー権限を付与してから再実行してください")


def install_frida_server():
    """frida-server をダウンロードして端末にインストール"""
    print("\n[4/5] frida-server インストール...")

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
    print("\n[5/5] セットアップ完了！")
    print("=" * 60)
    print()
    print("📋 次のステップ:")
    print()
    print("1️⃣  mitmproxy を起動 (PC側):")
    print(f'   {sys.executable} -m mitmweb -s capture_addon.py --listen-port 8080')
    print()
    print("2️⃣  frida-server を起動 (別ターミナルで):")
    print(f'   {ADB} shell "su -c /data/local/tmp/frida-server &"')
    print()
    print("3️⃣  Android端末のWiFiプロキシを設定:")
    print("   設定 → WiFi → 接続中のネットワーク → プロキシ → 手動")
    print("   ホスト: <PCのIPアドレス>")
    print("   ポート: 8080")
    print()
    print("   PCのIPアドレスを確認:")
    print("   ipconfig で WiFi アダプタの IPv4 アドレスを確認")
    print()
    print("4️⃣  SSL Pinning バイパス + アプリ起動:")
    venv_frida = Path(__file__).parent / ".venv" / "Scripts" / "frida.exe"
    print(f'   {venv_frida} -U -f jp.pokemon.pokemonsleep -l frida_ssl_bypass.js --no-pause')
    print()
    print("5️⃣  アプリでボックスを開く → mitmweb (http://localhost:8081) で通信を確認")
    print()
    print("=" * 60)


def main():
    print("=" * 60)
    print("  Pokemon Sleep - Android セットアップ")
    print("=" * 60)

    check_device()
    check_root()
    install_ca_cert()
    install_frida_server()
    print_next_steps()


if __name__ == "__main__":
    main()
