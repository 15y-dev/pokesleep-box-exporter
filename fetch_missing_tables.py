"""
既存のダンプに不足しているマスターテーブルを追加取得するスクリプト
Usage: アプリ起動中に python fetch_missing_tables.py を実行
"""
import frida
import json
import sys
import time
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FRIDA_SCRIPT = """
var sqlcipher = Process.findModuleByName("libsqlcipher.so");
var sqlite3_prepare_v2 = new NativeFunction(sqlcipher.findExportByName("sqlite3_prepare_v2"), 'int', ['pointer','pointer','int','pointer','pointer']);
var sqlite3_step_fn = new NativeFunction(sqlcipher.findExportByName("sqlite3_step"), 'int', ['pointer']);
var sqlite3_column_text = new NativeFunction(sqlcipher.findExportByName("sqlite3_column_text"), 'pointer', ['pointer','int']);
var sqlite3_column_count = new NativeFunction(sqlcipher.findExportByName("sqlite3_column_count"), 'int', ['pointer']);
var sqlite3_column_name = new NativeFunction(sqlcipher.findExportByName("sqlite3_column_name"), 'pointer', ['pointer','int']);
var sqlite3_finalize = new NativeFunction(sqlcipher.findExportByName("sqlite3_finalize"), 'int', ['pointer']);
var sqlite3_db_filename = new NativeFunction(sqlcipher.findExportByName("sqlite3_db_filename"), 'pointer', ['pointer','pointer']);
var sqlite3_step_hook = sqlcipher.findExportByName("sqlite3_step");

var dbHandles = {};
var serverDb = null; var masterDb = null;

function runQ(db, sql) {
    var sp = Memory.alloc(8); var tp = Memory.alloc(8);
    var rc = sqlite3_prepare_v2(db, Memory.allocUtf8String(sql), -1, sp, tp);
    if (rc !== 0) return [];
    var stmt = sp.readPointer();
    var cc = sqlite3_column_count(stmt);
    var cols = [];
    for (var i=0;i<cc;i++) cols.push(sqlite3_column_name(stmt,i).readUtf8String());
    var rows = [];
    while (sqlite3_step_fn(stmt) === 100) {
        var r = {};
        for (var j=0;j<cc;j++) {
            var v = sqlite3_column_text(stmt,j);
            r[cols[j]] = v.isNull() ? null : v.readUtf8String();
        }
        rows.push(r);
    }
    sqlite3_finalize(stmt);
    return rows;
}

Interceptor.attach(sqlite3_step_hook, {
    onEnter: function(args) {
        if (serverDb && masterDb) return;
        try {
            var dbPtr = args[0].readPointer();
            var k = dbPtr.toString();
            if (!dbHandles[k]) {
                var fn = sqlite3_db_filename(dbPtr, Memory.allocUtf8String("main")).readUtf8String();
                dbHandles[k] = fn;
                if (fn.indexOf("masterdata_server.db") !== -1) masterDb = dbPtr;
                else if (fn.indexOf("server.db") !== -1) serverDb = dbPtr;
                if (serverDb && masterDb) {
                    setTimeout(function() { send({type:"ready"}); }, 1000);
                }
            }
        } catch(e) {}
    }
});

rpc.exports = {
    query: function(dbName, sql) {
        var db = dbName === "server" ? serverDb : masterDb;
        if (!db) return JSON.stringify([]);
        return JSON.stringify(runQ(db, sql));
    },
    status: function() {
        return JSON.stringify({server: !!serverDb, master: !!masterDb, handles: dbHandles});
    }
};
"""


def main():
    device = frida.get_usb_device()
    pid = None
    for proc in device.enumerate_processes():
        if "pokemonsleep" in proc.name.lower().replace("é","e") or "jp.pokemon.pokemonsleep" in proc.name:
            pid = proc.pid
            break
    if not pid:
        import subprocess
        r = subprocess.run(["D:\\android\\platform-tools\\adb.exe", "shell", "pidof jp.pokemon.pokemonsleep"],
                          capture_output=True, text=True)
        if r.stdout.strip():
            pid = int(r.stdout.strip())
    if not pid:
        print("❌ Pokemon Sleep not running!")
        sys.exit(1)

    print(f"✅ Attaching to PID {pid}...")
    session = device.attach(pid)
    script = session.create_script(FRIDA_SCRIPT)

    ready = [False]
    def on_message(msg, data):
        if msg.get("type") == "send" and msg.get("payload", {}).get("type") == "ready":
            ready[0] = True
            print("✅ DB handles ready!")
        else:
            print(f"[msg] {msg}")

    script.on("message", on_message)
    script.load()

    print("📱 アプリを操作してください...")
    for i in range(30):
        if ready[0]:
            break
        time.sleep(1)
        if i % 5 == 4:
            print(f"  ...待機中 ({i+1}s)")

    if not ready[0]:
        status = json.loads(script.exports_sync.status())
        print(f"Status: {status}")
        if not status["master"]:
            print("❌ Master DB not found.")
            session.detach()
            sys.exit(1)

    # Step 1: テーブル一覧取得
    print("\n📋 マスターDBのテーブル一覧:")
    tables = json.loads(script.exports_sync.query("master",
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))
    table_names = [t["name"] for t in tables]
    for t in table_names:
        print(f"  - {t}")

    # Step 2: pickup/carry 関連テーブルを探して取得
    print("\n🔍 pickup/carry 関連テーブルを検索...")
    carry_tables = [t for t in table_names if any(k in t.lower() for k in
        ["pickup", "carry", "inventory", "item_capacity", "base_stat", "pokemon_stat"])]
    
    if not carry_tables:
        # 全テーブルから max_carry 系カラムを持つものを探す
        print("  直接名称が見つからないため、全テーブルのカラムを調査...")
        for tname in table_names:
            try:
                sample = json.loads(script.exports_sync.query("master",
                    f"SELECT * FROM {tname} LIMIT 1"))
                if sample:
                    cols = list(sample[0].keys())
                    has_carry = any(k for k in cols if any(w in k.lower() for w in
                        ["carry", "max_own", "inventory", "capacity", "berry"]))
                    if has_carry:
                        carry_tables.append(tname)
                        print(f"  ✅ {tname}: {cols}")
            except:
                pass

    # Step 3: 見つかったテーブルのデータを取得してダンプに追加
    dump_path = os.path.join(BASE_DIR, "pokemon_box_dump.json")
    with open(dump_path, encoding="utf-8") as f:
        dump = json.load(f)

    new_tables = {}
    for tname in carry_tables:
        try:
            rows = json.loads(script.exports_sync.query("master", f"SELECT * FROM {tname}"))
            new_tables[tname] = rows
            print(f"\n📊 {tname}: {len(rows)} rows")
            if rows:
                print(f"   columns: {list(rows[0].keys())}")
                print(f"   sample: {rows[0]}")
        except Exception as e:
            print(f"  {tname}: ERROR - {e}")

    if new_tables:
        dump.update(new_tables)
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=2)
        print(f"\n✅ {len(new_tables)} tables added to {dump_path}")

        # CSV再生成
        from dump_pokemon_box import build_csv
        build_csv(dump)
    else:
        print("\n⚠️ pickup/carry関連テーブルが見つかりませんでした")
        print("   テーブル一覧を参照して手動で探してください")

    session.detach()
    print("\n🎉 完了！")


if __name__ == "__main__":
    main()
