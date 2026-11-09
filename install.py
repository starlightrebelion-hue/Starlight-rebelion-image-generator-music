"""Instala el script FLBridge en la carpeta Hardware de FL Studio."""
import shutil

from flbridge import ROOT, settings_dir


def main() -> None:
    target = settings_dir() / "Hardware" / "FLBridge" / "device_FLBridge.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "fl_side" / "device_FLBridge.py", target)
    print(f"Instalado en {target}")


if __name__ == "__main__":
    main()
