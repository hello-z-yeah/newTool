# PySide6 migration

The runtime interface has been migrated from CustomTkinter/Tkinter to PySide6.
The protocol parser, serial worker, raw saver and command library remain the
existing framework-independent backend modules.

## Install

```bat
python -m pip install -r requirements.txt
```

## Run

```bat
python main.py
```

Optional initial serial settings:

```bat
python main.py --port COM3 --baud 115200
```

## Main changes

- Native Qt main window and layouts; no CustomTkinter runtime dependency.
- Five independent white cards: navigation, serial configuration, live data,
  send area and status bar.
- Unified three-state Qt buttons. Toggle buttons keep the pressed appearance
  while enabled.
- Native editable 40-row HEX/ASCII command library.
- Thread-safe receive queue drained by a 30 ms `QTimer`.
- Hover-only scroll bars when content overflows.
- Existing backend JSON formats and command-library migration are preserved.

The distributed project contains no CustomTkinter runtime dependency.
