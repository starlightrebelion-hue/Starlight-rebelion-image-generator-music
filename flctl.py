"""CLI de FL Studio. Ejemplos:
  flctl.py status
  flctl.py tempo 128
  flctl.py call mixer setTrackVolume 1 0.8
  flctl.py functions mixer
  flctl.py theme list
  flctl.py theme apply Vino
  flctl.py theme reset
  flctl.py preset list
  flctl.py preset run trap_140
  flctl.py render cancion.flp mp3
"""
import argparse
import json
import sys

import flbridge as fl


def _value(text: str):
    if text in ("true", "false"):
        return text == "true"
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            pass
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("status", "play", "stop"):
        sub.add_parser(name)
    sub.add_parser("tempo").add_argument("bpm", type=float)
    sub.add_parser("functions").add_argument("module")
    export = sub.add_parser("render")
    export.add_argument("project")
    export.add_argument("format", nargs="?", default="wav", choices=["wav", "mp3"])
    raw = sub.add_parser("call")
    raw.add_argument("module")
    raw.add_argument("function")
    raw.add_argument("args", nargs="*", type=_value)
    for name, actions in (("theme", ["list", "apply", "reset"]), ("preset", ["list", "run"])):
        group = sub.add_parser(name)
        group.add_argument("action", choices=actions)
        group.add_argument("name", nargs="?")
    args = parser.parse_args()

    try:
        if args.cmd == "status":
            out = fl.status()
        elif args.cmd == "play":
            # transport.start alterna play/pausa: solo se llama si esta detenido
            out = None if fl.call("transport", "isPlaying") else fl.call("transport", "start")
        elif args.cmd == "stop":
            out = fl.call("transport", "stop")
        elif args.cmd == "tempo":
            out = fl.call("bridge", "setTempo", args.bpm)
        elif args.cmd == "functions":
            out = fl.call("bridge", "functions", args.module)
        elif args.cmd == "render":
            out = str(fl.render(args.project, args.format))
        elif args.cmd == "call":
            out = fl.call(args.module, args.function, *args.args)
        elif args.cmd == "theme":
            if args.action == "list":
                out = fl.list_themes()
            elif args.action == "apply":
                out = str(fl.apply_theme(args.name))
            else:
                out = fl.reset_theme()
        else:
            out = fl.list_presets() if args.action == "list" else fl.run_preset(args.name)
    except fl.FLError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
