# EasyKey

A usability-first desktop interface for keyboard firmware configuration.

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

## Project Structure

```
easykey/
  detection/       # HID scanning, VIA/Vial protocol clients
  layouts/         # SQLite layout DB, KLE parser
  ui/              # Tkinter app, wizard, picker, test mode
  models/          # Keymap, undo/redo, snapshots
build/             # PyInstaller specs
tests/             # Unit tests
```

## Features (v1)

- **First-run wizard** — guided onboarding for new users
- **Automatic keyboard detection** — VIA/Vial HID enumeration
- **Visual layout rendering** — KLE-based keyboard canvas
- **Click-to-remap picker** — searchable, categorized binding selection
- **Layer visualization** — tabs with diff view and reordering
- **Undo / Redo** — full command stack with descriptive labels
- **Staged preview & Apply** — review before writing to keyboard
- **Test mode** — live keystroke visualizer with mismatch detection
- **Accessibility** — keyboard navigation, high-contrast mode, font scaling

## Tests

```bash
python tests/test_keymap.py
python tests/test_kle_parser.py
python tests/test_database.py
```

## Packaging

```bash
# macOS
pyinstaller build/easykey-macos.spec

# Windows
pyinstaller build/easykey-windows.spec
```

## License

MIT
