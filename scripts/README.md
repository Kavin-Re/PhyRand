# Legacy scripts

These file names predate the `phyrand` package. They are kept as thin
wrappers so existing habits and notes keep working; new work should use the
`phyrand` command.

| Script | Now equivalent to | Change from the original |
| :--- | :--- | :--- |
| `quantum_vault.py` | `phyrand encrypt`, `phyrand vault list`, `phyrand vault revoke` (menu) | Device bytes are health-tested and conditioned instead of being used raw as the key; the vault is written atomically; keys are no longer printed |
| `quick_encrypt.py FILE` | `phyrand encrypt --allow-os-fallback FILE` | Mixes in device entropy when the board is healthy and says which source was used |
| `auto_unlock.py` | `phyrand decrypt FILE --file-id ID --url URL` | Server URL comes from `PHYRAND_API_URL` instead of a hard-coded tunnel address; accepts a per-file release token |
| `receiver_decrypt.py` | `phyrand decrypt FILE --key-prompt` | Key is read without echo; plaintext is written to a file, not printed |
| `analyze.py [FILE] [--plot]` | `phyrand analyze FILE` | Prints statistics with the standard library; the random-walk plot is optional (`requirements-viz.txt`) and no longer runs on import |
| `live_view.py --port PORT` | (no CLI equivalent) | Port is an argument; clean exit on timeout |

Run them from the repository root, for example
`python scripts/analyze.py data/random_whitened.bin`.
