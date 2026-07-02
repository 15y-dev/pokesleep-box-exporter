"""
Frida経由でポケモンスリープのDBからボックスデータをダンプしてCSVに変換
"""
import frida
import json
import sys
import time
import csv
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


def load_pokemon_data():
    """pokemon_data.json からマスターデータ定義を読み込む"""
    data_path = os.path.join(BASE_DIR, "pokemon_data.json")
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # _comment キーを除去
    def clean(d):
        if isinstance(d, dict):
            return {k: v for k, v in d.items() if not k.startswith("_")}
        return d
    return {k: clean(v) for k, v in data.items() if not k.startswith("_")}


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

    print("📱 アプリを操作してください（ボックスを開くなど）...")
    for i in range(30):
        if ready[0]:
            break
        time.sleep(1)
        if i % 5 == 4:
            print(f"  ...待機中 ({i+1}s)")

    if not ready[0]:
        status = json.loads(script.exports_sync.status())
        print(f"Status: {status}")
        if not status["server"] or not status["master"]:
            print("❌ DB handles not found. Operate the app and try again.")
            session.detach()
            sys.exit(1)

    print("\n📊 データ取得中...")

    tables = {
        "server": [
            ("user_support_pokemons", "SELECT * FROM user_support_pokemons"),
            ("user_support_teams", "SELECT * FROM user_support_teams"),
            ("user_pokemon_friend", "SELECT * FROM user_pokemon_friend"),
            ("user_wild_pokemon", "SELECT * FROM user_wild_pokemon"),
            ("user_main", "SELECT * FROM user_main LIMIT 1"),
        ],
        "master": [
            ("pokemons", "SELECT * FROM pokemons"),
            ("pokedex_data", "SELECT * FROM pokedex_data"),
            ("pokemon_nature", "SELECT * FROM pokemon_nature"),
            ("pokemon_main_skills", "SELECT * FROM pokemon_main_skills"),
            ("pokemon_types", "SELECT * FROM pokemon_types"),
            ("pokemon_rankup_bonus", "SELECT * FROM pokemon_rankup_bonus"),
            ("pokemon_pickup_status", "SELECT * FROM pokemon_pickup_status"),
        ]
    }

    all_data = {}
    for db_name, queries in tables.items():
        for table_name, sql in queries:
            try:
                result = json.loads(script.exports_sync.query(db_name, sql))
                all_data[table_name] = result
                print(f"  {table_name}: {len(result)} rows")
            except Exception as e:
                print(f"  {table_name}: ERROR - {e}")
                all_data[table_name] = []

    json_path = os.path.join(BASE_DIR, "pokemon_box_dump.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ JSON saved: {json_path}")

    build_csv(all_data)

    session.detach()
    print("\n🎉 完了！")


def build_csv(data):
    """JSONダンプからCSVを生成"""
    pdata = load_pokemon_data()
    POKEDEX_NAMES = pdata["pokedex_names"]
    NATURE_NAMES = pdata["nature_names"]
    SUBSKILL_NAMES = pdata["subskill_names"]
    SPECIALTY_NAMES = pdata["specialty_names"]
    FIELD_NAMES = pdata["field_names"]
    POKEMON_MAIN_SKILL = pdata["pokemon_main_skill"]
    POKEMON_SPECIALTY = pdata.get("pokemon_specialty", {})
    BERRY_NAMES = pdata.get("berry_names", {})
    INGREDIENT_NAMES = pdata.get("ingredient_names", {})

    # Build pokemon master lookup by id
    pokemon_master = {p.get("id"): p for p in data.get("pokemons", [])}

    # Build pickup status lookup (berry, max carry)
    pickup_status = {}
    for ps in data.get("pokemon_pickup_status", []):
        pickup_status[ps.get("pokemon_id")] = ps

    # ポケモンタイプからきのみを導出（berry_id = type_id）
    # pokemon_pickup_status がない場合のフォールバック
    pokemon_type_berry = {}
    for p in data.get("pokemons", []):
        pokemon_type_berry[p.get("id")] = p.get("type", "")

    # Determine which table has box pokemon
    box_pokemon = data.get("user_pokemon_friend", [])
    if not box_pokemon:
        box_pokemon = data.get("user_support_pokemons", [])
    if not box_pokemon:
        box_pokemon = data.get("user_wild_pokemon", [])

    if not box_pokemon:
        print("❌ No Pokemon data found!")
        return

    print(f"\n📋 Pokemon columns: {list(box_pokemon[0].keys())}")

    csv_path = os.path.join(BASE_DIR, "pokemon_box.csv")

    from datetime import datetime, timezone, timedelta
    JST = timezone(timedelta(hours=9))

    def ts_to_date(ts_str):
        try:
            ts = int(ts_str)
            if ts <= 0: return ""
            return datetime.fromtimestamp(ts, tz=JST).strftime("%Y/%m/%d %H:%M")
        except:
            return ts_str or ""

    # ゲーム画面の表示順に準拠
    out_cols = [
        # 基本情報（トップ画面）
        "図鑑No", "ポケモン名", "Lv", "SP", "性別", "とくい", "リボンランク", "お気に入り",
        
        # おてつだい能力
        "きのみ", "食材A", "食材B", "食材C", "最大所持数",
        # メインスキル・サブスキル
        "メインスキル", "メインスキルLv",
        "サブスキル1", "サブスキル2", "サブスキル3", "サブスキル4", "サブスキル5",
        # 詳細ステータス
        "せいかく", "出会った日", "出会ったフィールド",
        # 補足
        "げんき","きのみSP", "料理SP", "スキルSP", "進化回数", "個体ID",
    ]

    gender_map = {"1": "♂", "2": "♀", "0": "-"}
    fav_map = {"0": "", "1": "★"}

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=out_cols, extrasaction='ignore')
        writer.writeheader()

        for poke in box_pokemon:
            type_num = poke.get("TypeNumber", "")
            master = pokemon_master.get(type_num, {})
            pokedex_no = master.get("pokedex_order_id", master.get("image_id", ""))
            # 通常: 図鑑Noで名前解決。リージョンフォーム・特別衣装(TN>=1000)はTypeNumberで解決
            if int(type_num) >= 1000:
                pokemon_name = POKEDEX_NAMES.get(str(type_num))
            else:
                pokemon_name = None
            if not pokemon_name:
                pokemon_name = POKEDEX_NAMES.get(str(pokedex_no))
            if not pokemon_name:
                pokemon_name = master.get("name", f"Pokemon#{type_num}")

            nature_id = poke.get("Nature", "")
            nature_name = NATURE_NAMES.get(nature_id, f"性格#{nature_id}")

            # とくいは種族固定（DBのSpecialtyフィールドは不正確）
            specialty_name = POKEMON_SPECIALTY.get(type_num, SPECIALTY_NAMES.get(poke.get("Specialty", ""), "不明"))

            main_skill = POKEMON_MAIN_SKILL.get(type_num, "不明")

            # おてつだい能力
            ps = pickup_status.get(type_num, {})
            berry_id = ps.get("normal_berry_id", "")
            if not berry_id:
                # フォールバック: ポケモンタイプ = きのみID（Sleep仕様）
                berry_id = pokemon_type_berry.get(type_num, "")
            berry_name = BERRY_NAMES.get(berry_id, f"きのみ#{berry_id}") if berry_id else ""
            max_carry = ps.get("max_own_item_count", "")

            def fmt_ingredient(item_id, item_num):
                if not item_id or item_id == "0": return ""
                name = INGREDIENT_NAMES.get(item_id, f"食材#{item_id}")
                return f"{name} x{item_num}" if item_num else name

            ingredient_a = fmt_ingredient(poke.get("PickupItemId1"), poke.get("PickupItemNum1"))
            ingredient_b = fmt_ingredient(poke.get("PickupItemId2"), poke.get("PickupItemNum2"))
            ingredient_c = fmt_ingredient(poke.get("PickupItemId3"), poke.get("PickupItemNum3"))

            row = {
                "図鑑No": pokedex_no,
                "ポケモン名": pokemon_name,
                "Lv": poke.get("Rank", ""),
                "SP": poke.get("SP", ""),
                "性別": gender_map.get(poke.get("Gender", ""), "?"),
                "とくい": specialty_name,
                "リボンランク": poke.get("CurrentRibbonRank", ""),
                "お気に入り": fav_map.get(poke.get("Favorited", ""), ""),
                "きのみ": berry_name,
                "食材A": ingredient_a,
                "食材B": ingredient_b,
                "食材C": ingredient_c,
                "最大所持数": max_carry,
                "げんき": poke.get("PowerValue", ""),
                "メインスキル": main_skill,
                "メインスキルLv": poke.get("MainSkillLevelValue", ""),
                "サブスキル1": SUBSKILL_NAMES.get(poke.get("SubSkill1", ""), "") if poke.get("SubSkill1", "0") != "0" else "",
                "サブスキル2": SUBSKILL_NAMES.get(poke.get("SubSkill2", ""), "") if poke.get("SubSkill2", "0") != "0" else "",
                "サブスキル3": SUBSKILL_NAMES.get(poke.get("SubSkill3", ""), "") if poke.get("SubSkill3", "0") != "0" else "",
                "サブスキル4": SUBSKILL_NAMES.get(poke.get("SubSkill4", ""), "") if poke.get("SubSkill4", "0") != "0" else "",
                "サブスキル5": SUBSKILL_NAMES.get(poke.get("SubSkill5", ""), "") if poke.get("SubSkill5", "0") != "0" else "",
                "せいかく": nature_name,
                "出会った日": ts_to_date(poke.get("CapturedTime", "")),
                "出会ったフィールド": FIELD_NAMES.get(poke.get("CapturedField", ""), poke.get("CapturedField", "")),
                "きのみSP": poke.get("BerrySP", ""),
                "料理SP": poke.get("CookingSP", ""),
                "スキルSP": poke.get("SkillSP", ""),
                "進化回数": poke.get("EvolutionCount", ""),
                "個体ID": poke.get("PokemonId", ""),
            }
            writer.writerow(row)

    print(f"✅ CSV saved: {csv_path} ({len(box_pokemon)} Pokemon)")

    # Also save raw CSV with all columns
    raw_csv_path = os.path.join(BASE_DIR, "pokemon_box_raw.csv")
    with open(raw_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        all_cols = list(box_pokemon[0].keys())
        writer = csv.DictWriter(f, fieldnames=all_cols, extrasaction='ignore')
        writer.writeheader()
        for poke in box_pokemon:
            writer.writerow(poke)
    print(f"✅ Raw CSV saved: {raw_csv_path}")


if __name__ == "__main__":
    main()
