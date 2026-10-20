# Third-party code

Herdr Lens's original Python code is MIT licensed; see `LICENSE`.

- **Herdr File Viewer**, by Saeed Marzban, MIT: <https://github.com/smarzban/herdr-file-viewer>.
  The optional native viewer is based on v1.18.0, with our opt-in file-open request channel,
  direct content focus, modal deferral, tests, and prerelease version handling.
  Its license is in `licenses/herdr-file-viewer-MIT.txt`.
- **Herdr**, Apache-2.0: <https://github.com/herdrdev/herdr>.
  The optional 0.9.3 companion changes the client-side Ctrl+click path resolution and its tests.
  The server protocol is unchanged. Its license is in `licenses/herdr-Apache-2.0.txt`.
  The Herdr patch and derivative component are distributed under Apache-2.0.
- **Textual / Rich / Markdown-it-py** provide the built-in Python renderer. Exact versions
  and dependency hashes are recorded in `uv.lock` and `requirements.txt`; installed packages
  retain their license files.

Pinned commits and modifications are recorded in `upstream.json` and `patches/`.
`licenses/native-dependency-licenses.txt` and the matching release asset contain bundled native dependency notices.
This is an independent plugin; it is not an official release from either upstream project.
