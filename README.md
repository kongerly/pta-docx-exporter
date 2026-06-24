# PTA DOCX Exporter

A Windows desktop tool for exporting PTA (Pintia) problem sets into structured Word (`.docx`) documents.

It is designed for cases where you need to review, organize, print, or archive problem content from PTA in a cleaner offline format.

## Features

- Desktop UI built with `Python + Tkinter`
- Reuses a real browser login session through `Node + Playwright`
- Supports exporting either:
  - an entire problem set
  - a single question type inside a problem set
- Generates structured `.docx` output for easier reading and printing
- Can download and embed images from problem statements
- Preserves export warnings when some problems or images cannot be fetched

## Supported Content

The current parser includes handling for common PTA exam and assignment pages such as:

- true/false questions
- single-choice questions
- multiple-choice questions
- fill-in-the-blank questions

## Environment

- Windows 10/11
- Python `3.12+`
- Microsoft Edge or Google Chrome
- Node runtime with Playwright dependencies

## Install

```powershell
python -m pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

## Typical Workflow

1. Open the PTA login page from the app.
2. Complete login in the browser window.
3. Confirm the detected account.
4. Load available problem sets.
5. Select the problem set or question type you want to export.
6. Choose merged or separate Word export mode.
7. Export to `.docx`.

## Configuration

Core configuration is defined in [config.py](config.py):

- `start_url`
- `output_dir`
- `session_profile_dir`
- `temp_dir`
- `embed_images`

## Build

To build the Windows package:

```powershell
pwsh .\build\build.ps1 -PythonExe python
```

To explicitly provide a Node runtime:

```powershell
pwsh .\build\build.ps1 `
  -PythonExe python `
  -NodeExe "C:\path\to\node.exe" `
  -NodeModulesDir "C:\path\to\node_modules"
```

To verify packaging only in CI:

```powershell
pwsh .\build\build.ps1 -PythonExe python -SkipRuntimeCopy
```

## Tests

```powershell
python -m unittest discover -s tests -v
```

If you keep raw PTA HTML snapshots locally for parser regression tests, place them under:

- `private/raw_pta_html/1.html`
- `private/raw_pta_html/2.html`
- `private/raw_pta_html/3.html`
- `private/raw_pta_html/4.html`

These files are intentionally ignored by Git and are not meant to be committed to a public repository.

## Privacy Notes

- This project does not bypass PTA login. It only reuses a login session that you complete in your own browser environment.
- Browser profile data and session data should stay local and must not be committed.
- Raw HTML saved directly from PTA pages may contain sensitive information such as real names, course titles, or problem set identifiers. Keep such files only in ignored local directories like `private/raw_pta_html/`.
- Use this tool only for courses, problem sets, and accounts you are authorized to access.

## Limitations

- Currently developed and tested for Windows only
- Relies on the current PTA page structure
- May require parser updates if Pintia changes its frontend significantly
- Image downloads may fail because of network limits, timeouts, or source availability; export will still continue with warnings

## Changelog

See [CHANGELOG.md](CHANGELOG.md).
