# Yomu Note font setup

Yomu ships three optional SIL Open Font License (OFL 1.1) families:

- **Montserrat** (default application UI): buttons, toolbars, tabs, settings, menus, labels, dialogs. Normal and italic variable-weight TTF fonts.
- **Mochiy Pop One** (wordmark): the large `Yomu ❤` logo and branding.
- **Nunito** (fallback and notes option): available for notes text and as the application fallback if Montserrat is unavailable.

**Your notes are separate from the UI font.** Changing the application's interface font does not overwrite custom fonts inside `.yominote` projects or change the default notes font setting. Existing projects will retain their formatting.

## Building with bundled fonts (Windows, macOS or Linux)

The existing `build-windows.ps1`, `build-mac.command` and `build-linux.sh` each call `fetch_fonts.py` before PyInstaller. That script downloads official Google Fonts source files and their `OFL.txt` licence notices under `assets/fonts/<family>/`. PyInstaller bundles the entire `assets/` directory into the standalone app, so Yomu can run fully offline afterward.

The build computer needs internet once to fetch fonts (or can reuse previously downloaded local font assets). If downloading is unavailable, the app falls back to locally installed fonts. The source ZIP intentionally does **not** contain downloaded font binaries.

To download manually before building:

- Windows PowerShell: `& .\.venv\Scripts\python.exe fetch_fonts.py`
- macOS/Linux: `.venv/bin/python fetch_fonts.py`

After the font setup completes, use your normal platform build command. Do not remove a font's `OFL.txt` notice when redistributing a build that contains it.
