# Pokemon Sleep Box CSV Exporter

> 📖 [日本語版 README はこちら](README_ja.md)

Extract your Pokemon Sleep box data from the in-app database and export it as a Japanese-localized CSV.

<img width="1823" height="975" alt="image" src="https://github.com/user-attachments/assets/710ee4a6-04b0-4e72-98b5-33ee1d62f45a" />

## Requirements

- Windows PC
- Rooted Android device (USB connection)
- [Frida](https://frida.re/) (Python package + frida-server on device)

## Setup

### 1. Python Environment

```bash
python -m venv .venv
.venv\Scripts\activate
pip install frida frida-tools
```

### 2. Android Device Setup (Automated)

```bash
python setup_android.py
```

Automatically downloads and installs frida-server on the device.

## Usage

### Dump Box Data → CSV

```bash
# 1. Start frida-server
adb shell "su -c '/data/local/tmp/frida-server &'"

# 2. Launch the app and open your Pokemon box

# 3. Dump data + generate CSV
python dump_pokemon_box.py
```

Output files:
- `pokemon_box.csv` — CSV with Japanese column names (30 columns)
- `pokemon_box_raw.csv` — Raw DB data CSV
- `pokemon_box_dump.json` — Full DB dump (JSON)

### Regenerate CSV Only (from existing dump)

```bash
python -c "import json; from dump_pokemon_box import build_csv; build_csv(json.load(open('pokemon_box_dump.json', encoding='utf-8')))"
```

### Fetch Missing Tables

```bash
python fetch_missing_tables.py
```

Scans the master DB for additional tables and adds them to the existing dump.

## HTML Viewer

Open `pokemon_box_viewer.html` in a browser and drag & drop the CSV file to view it as a table.

- Column sorting (click headers)
- Show/hide columns ("📋 列の表示" button)
- Settings saved in localStorage

### 📊🔍 Daifuku Checker Integration

Auto-fill the [Pokemon Sleep Daifuku](https://www.pokemonsleepdaifuku.com/) checkers directly from the viewer.

- **📊 期待値** — [Expected Value Checker](https://www.pokemonsleepdaifuku.com/checker/expected/)
- **🔍 個体値** — [IV Checker](https://www.pokemonsleepdaifuku.com/checker/)

1. Click a row in the table to select a Pokemon
2. Click "📊 期待値" or "🔍 個体値" button → JS code is copied to clipboard
3. Open the corresponding Daifuku checker page
4. Paste into the URL bar → press `Enter` to execute

> ⚠️ **Chrome note:** Chrome strips the `javascript:` prefix when pasting. Manually type `javascript:` at the beginning after pasting.

- Pre-evolution Pokemon are automatically mapped to their final evolution (e.g., Bulbasaur → Venusaur)
- Branching evolutions (e.g., Eevee) require manual Pokemon name selection

## File Structure

```
pokemonsleep/
├── dump_pokemon_box.py       # Main: Frida → DB → CSV
├── fetch_missing_tables.py   # Helper: fetch missing tables
├── pokemon_data.json         # Master data definitions (Japanese names etc.)
├── pokemon_box_viewer.html   # CSV viewer (HTML)
├── setup_android.py          # Android device setup
├── README_ja.md              # Japanese README
├── README.md                 # English README
└── .gitignore
```

## Notes

- This project is for educational and research purposes
- App-derived data (DB files, dump JSON, CSV) should not be included in git due to copyright
