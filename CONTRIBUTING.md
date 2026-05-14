# Contributing to Yaz

Thanks for considering a contribution!

## Dev setup

```bash
git clone https://github.com/yetesfa/yaz.git
cd yaz
./install.sh        # installs deps + creates ./.venv with PyQt6
```

Run the app:

```bash
.venv/bin/python yaz.py          # straight from source, no install needed
# or
yaz                              # if you already symlinked via install.sh
```

## Project layout (single file by design)

The whole app lives in `yaz.py`. It's organised as:

1. **Capture backends** (`capture_full_screen`, `capture_via_portal`, …)
2. **Region picker** (`pick_region_from`)
3. **`run_app()`** — main entry. Defines the Qt classes inline as nested
   classes so PyQt6 is imported lazily (the portal mainloop is purely
   `Gio`-based and must stay Qt-free).
4. **Helpers** (`friendly_screen_name`, `describe_screen`, …)

If the file grows past ~2k lines, we'll split it into a package; for now
the all-in-one structure keeps it easy to fork.

## Style

- Plain Python, no formatter enforced — match what's already there.
- Type hints where they aid readability; don't bother annotating every
  internal helper.
- Comments explain **why**, not what. The why is the bit that goes stale
  if you don't write it down.

## Testing changes

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
import yaz, sys
sys.argv = ['yaz']
yaz.main()  # spins up the offscreen window for quick checks
"
```

For UI changes, just run `yaz` and use it for a minute — there's no
automated UI test harness yet.

## Pull requests

1. Open an issue first for anything non-trivial — saves rework.
2. Keep PRs focused. One concern per PR.
3. Update the README / About dialog if you add a user-visible feature.

## License

By contributing, you agree your changes are released under the project's
MIT licence (see `LICENSE`).
