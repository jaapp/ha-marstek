# Release Tooling

`tools/release.py` automates Marstek Local API releases by bumping manifest
versions, creating commits/tags, and optionally pushing or opening GitHub releases.

## Interactive workflow

Running the script without arguments launches an interactive wizard:

```bash
python tools/release.py
```

The wizard mirrors the grinder release flow: it inspects the latest tag, shows the
recent commit log, and offers numbered options (promote RC, patch/minor/major RC,
continue RC cycle, or provide a custom version). Once confirmed, it updates the
manifest(s), commits, tags, pushes, and creates the GitHub release. Enter `q` or
press `Ctrl+C` at any prompt to cancel.

## Non-interactive examples

```bash
# Create the next release candidate (auto-increment rc number)
python tools/release.py rc 1.2.0 --skip-github

# Create an explicit RC and skip the GitHub release
python tools/release.py rc 1.2.0 --rc-number 3 --skip-github

# Publish a final release with notes from a file and push everything
python tools/release.py final 1.2.0 --notes-file notes.md --push
```

Run `python tools/release.py --help` for the complete CLI reference.
