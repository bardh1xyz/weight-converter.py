# ⚖️ Weight Converter

A simple desktop weight converter made with Python and Tkinter.

Convert between **kilograms (kg)** and **pounds (lbs)** with a clean interface, conversion history, themes, and keyboard shortcuts.

![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![Tkinter](https://img.shields.io/badge/GUI-Tkinter-orange.svg)
![Version](https://img.shields.io/badge/version-3.0-green.svg)

## Features

* Convert between kg and lbs
* Live conversion as you type
* Light, dark, and system themes
* Conversion history with up to 12 entries
* Persistent settings and history
* Copy the full result or converted value
* Swap units quickly
* Full-screen mode
* Keyboard shortcuts
* No external Python packages required

## Requirements

* Python 3.8 or newer
* Tkinter

Tkinter is included with Python on Windows and macOS. On some Linux distributions, you may need to install it separately.

## Run

Clone the repository:

```bash
git clone https://github.com/bardh1xyz/weight-converter.py.git
cd weight-converter.py
```

Run the app:

```bash
python weight_converter.py
```

## Keyboard Shortcuts

| Shortcut           | Action               |
| ------------------ | -------------------- |
| `Enter`            | Convert              |
| `Esc` / `Ctrl + L` | Clear input          |
| `Ctrl + C`         | Copy full result     |
| `Ctrl + Shift + C` | Copy converted value |
| `Ctrl + Shift + S` | Swap units           |
| `Ctrl + Shift + L` | Clear history        |
| `F11`              | Toggle fullscreen    |
| `Ctrl + Q`         | Exit                 |

## Data

The app stores its settings and history locally in:

```text
~/.weight_converter/
```

This contains:

* `settings.json` — saved preferences, theme, units, and window settings
* `history.json` — saved conversion history

## Author

Made by [@bardhzzY](https://x.com/bardhzzYFN)

GitHub: [@bardh1xyz](https://github.com/bardh1xyz)

## License

This project is licensed under the MIT License.
