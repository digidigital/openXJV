import subprocess
import pathlib

BASE_DIR = pathlib.Path(__file__).parent

def convert():
    # Feste Pfade definieren
    ui_file = BASE_DIR / ".." / "ui" / "openxjv.ui"
    ui_py   = BASE_DIR / "openXJV_UI.py"

    # .ui konvertieren
    print(f"Konvertiere {ui_file} -> {ui_py}")
    subprocess.run(["pyside6-uic", str(ui_file), "-o", str(ui_py)], check=True)

    # Dateiinhalt lesen
    with ui_py.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    # Zeilen filtern
    new_lines = [line for line in lines if "import resources_rc" not in line]

    # Datei überschreiben
    with ui_py.open("w", encoding="utf-8") as f:
        f.writelines(new_lines)

if __name__ == "__main__":
    convert()
