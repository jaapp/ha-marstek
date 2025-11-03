#!/usr/bin/env python3
"""Automation helper for Marstek Local API releases.

This script manages release candidates and final releases by:
  * bumping manifest version numbers
  * creating a release commit
  * tagging the release
  * optionally pushing to origin
  * optionally creating a GitHub release (requires GITHUB_TOKEN)

Usage examples:
  # Create the next release candidate for 1.2.0 (auto-increments rc number)
  python tools/release.py rc 1.2.0

  # Create final release 1.2.0 with explicit notes and push/tag/release
  python tools/release.py final 1.2.0 --notes-file notes.md --push
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
import textwrap
from typing import Iterable, Sequence
from urllib import error, request

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_GLOB = "custom_components/*/manifest.json"


class ReleaseError(RuntimeError):
    """Raised for recoverable release issues."""


def run_git(
    args: Sequence[str],
    *,
    capture_output: bool = False,
    check: bool = True,
) -> str:
    """Run a git command in the repository root."""
    cmd = ["git", *args]
    print("+", " ".join(cmd))

    run_kwargs: dict[str, object] = {"cwd": REPO_ROOT, "text": True}
    if capture_output:
        run_kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE})
    else:
        run_kwargs["stderr"] = subprocess.PIPE

    result = subprocess.run(cmd, **run_kwargs)

    if check and result.returncode != 0:
        stderr = getattr(result, "stderr", "") or ""
        message = stderr.strip() or f"'git {' '.join(args)}' failed with {result.returncode}"
        raise ReleaseError(message)

    if capture_output:
        return result.stdout
    return ""


def ensure_clean_worktree() -> None:
    """Abort if the repository contains uncommitted changes."""
    status = run_git(["status", "--porcelain"], capture_output=True)
    if status.strip():
        raise ReleaseError(
            "Repository has uncommitted changes. Please commit or stash before releasing."
        )


def load_manifest_paths(explicit_paths: list[str] | None) -> list[Path]:
    """Return the manifest files to update."""
    if explicit_paths:
        manifests = [REPO_ROOT / path for path in explicit_paths]
    else:
        manifests = sorted(REPO_ROOT.glob(DEFAULT_MANIFEST_GLOB))

    if not manifests:
        raise ReleaseError(
            f"No manifest files found (searched for {DEFAULT_MANIFEST_GLOB})."
        )

    for manifest in manifests:
        if not manifest.exists():
            raise ReleaseError(f"Manifest file not found: {manifest}")

    return manifests


def update_manifest_versions(
    manifests: Iterable[Path],
    *,
    new_version: str,
    dry_run: bool,
) -> list[Path]:
    """Update the version field in manifest files."""
    updated: list[Path] = []
    for manifest in manifests:
        data = json.loads(manifest.read_text())
        old_version = data.get("version")
        if old_version == new_version:
            raise ReleaseError(
                f"{manifest.relative_to(REPO_ROOT)} already has version {new_version}."
            )
        data["version"] = new_version
        serialised = json.dumps(data, indent=2) + "\n"
        if dry_run:
            print(
                f"[dry-run] Would update {manifest.relative_to(REPO_ROOT)}: "
                f"{old_version} -> {new_version}"
            )
        else:
            manifest.write_text(serialised)
            updated.append(manifest)
    return updated


def validate_base_version(version: str) -> str:
    """Ensure version is in MAJOR.MINOR.PATCH format."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ReleaseError(f"Invalid base version '{version}'. Expected MAJOR.MINOR.PATCH.")
    return version


def compute_rc_version(
    base_version: str,
    *,
    rc_number: int | None,
) -> tuple[str, int]:
    """Determine release candidate version string."""
    tags_output = run_git(["tag"], capture_output=True)
    pattern = re.compile(rf"^v{re.escape(base_version)}\.rc(\d+)$")
    existing_rcs = [int(match.group(1)) for tag in tags_output.splitlines() if (match := pattern.match(tag))]

    if rc_number is None:
        rc_number = max(existing_rcs, default=0) + 1
    elif rc_number <= 0:
        raise ReleaseError("RC number must be positive.")
    elif rc_number in existing_rcs:
        raise ReleaseError(
            f"Release candidate v{base_version}.rc{rc_number} already exists."
        )

    rc_version = f"{base_version}.rc{rc_number}"
    return rc_version, rc_number


def get_latest_tag() -> str | None:
    """Return the latest reachable tag, if any."""
    try:
        tag = run_git(["describe", "--abbrev=0", "--tags"], capture_output=True).strip()
    except ReleaseError:
        return None
    return tag or None


def generate_release_notes(previous_tag: str | None) -> str:
    """Generate default release notes from git history."""
    if previous_tag:
        rev_range = f"{previous_tag}..HEAD"
    else:
        rev_range = "HEAD"

    try:
        log_output = run_git(
            ["log", rev_range, "--no-merges", "--pretty=format:- %s"],
            capture_output=True,
        )
    except ReleaseError:
        log_output = ""

    notes = log_output.strip()
    if not notes:
        notes = "No notable changes."
    return notes


def parse_repo_remote(remote: str) -> tuple[str, str]:
    """Extract owner/repo from git remote URL."""
    url = run_git(["remote", "get-url", remote], capture_output=True).strip()
    if url.startswith("git@github.com:"):
        path = url.split(":", 1)[1]
    elif url.startswith("https://github.com/"):
        path = url.split("github.com/", 1)[1]
    else:
        raise ReleaseError(f"Unsupported GitHub remote URL: {url}")

    if path.endswith(".git"):
        path = path[:-4]

    if path.count("/") != 1:
        raise ReleaseError(f"Unable to parse owner/repo from {url}")

    owner, repo = path.split("/")
    return owner, repo


def http_post_json(url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
    """Send a JSON POST request and return the parsed response."""
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            **headers,
        },
    )
    try:
        with request.urlopen(req) as resp:
            response_bytes = resp.read()
            return json.loads(response_bytes.decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise ReleaseError(
            f"GitHub API request failed ({exc.code}): {detail or exc.reason}"
        ) from exc


def create_github_release(
    *,
    tag_name: str,
    release_name: str,
    body: str,
    prerelease: bool,
    remote: str,
) -> None:
    """Create a release on GitHub."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ReleaseError(
            "GITHUB_TOKEN environment variable is required to create GitHub releases."
        )

    owner, repo = parse_repo_remote(remote)
    target_commitish = run_git(["rev-parse", "HEAD"], capture_output=True).strip()

    payload = {
        "tag_name": tag_name,
        "name": release_name,
        "body": body,
        "prerelease": prerelease,
        "target_commitish": target_commitish,
    }

    url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    print(f"+ POST {url}")
    response = http_post_json(url, payload, headers={"Authorization": f"Bearer {token}"})
    html_url = response.get("html_url")
    if html_url:
        print(f"Created GitHub release: {html_url}")


def build_parser() -> argparse.ArgumentParser:
    """Configure CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Create release candidates and final releases for Marstek Local API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              python tools/release.py rc 1.2.0
              python tools/release.py rc 1.2.0 --rc-number 3
              python tools/release.py final 1.2.0 --notes \"Bug fixes\" --push
            """
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_options(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--manifest",
            action="append",
            help="Manifest file(s) to update (defaults to custom_components/*/manifest.json).",
        )
        subparser.add_argument(
            "--notes",
            help="Release notes text. Overrides auto-generated notes.",
        )
        subparser.add_argument(
            "--notes-file",
            help="Path to a file containing release notes.",
        )
        subparser.add_argument(
            "--remote",
            default="origin",
            help="Git remote to push and use for GitHub releases (default: origin).",
        )
        subparser.add_argument(
            "--push",
            action="store_true",
            help="Push the release commit and tag to the remote.",
        )
        subparser.add_argument(
            "--skip-github",
            action="store_true",
            help="Skip creating a GitHub release.",
        )
        subparser.add_argument(
            "--skip-tag",
            action="store_true",
            help="Do not create a git tag.",
        )
        subparser.add_argument(
            "--skip-commit",
            action="store_true",
            help="Do not create a release commit.",
        )
        subparser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show actions without modifying anything.",
        )
        subparser.add_argument(
            "--commit-message",
            help="Custom commit message (default: Release <version>).",
        )

    final_parser = subparsers.add_parser(
        "final",
        help="Create a final release with the provided semantic version.",
    )
    final_parser.add_argument("version", help="Release version (MAJOR.MINOR.PATCH).")
    add_common_options(final_parser)

    rc_parser = subparsers.add_parser(
        "rc",
        help="Create a release candidate for the provided base version.",
    )
    rc_parser.add_argument("base_version", help="Base version (MAJOR.MINOR.PATCH).")
    rc_parser.add_argument(
        "--rc-number",
        type=int,
        help="Explicit RC number (default: next available).",
    )
    add_common_options(rc_parser)

    return parser


def read_notes(args: argparse.Namespace, previous_tag: str | None) -> str:
    """Determine release notes text."""
    if args.notes_file:
        path = Path(args.notes_file)
        if not path.exists():
            raise ReleaseError(f"Notes file not found: {path}")
        return path.read_text().strip()
    if args.notes:
        return args.notes.strip()
    return generate_release_notes(previous_tag)


def push_changes(remote: str, tag_name: str, *, push_tag: bool, push_branch: bool) -> None:
    """Push release commit and/or tag to the remote."""
    if push_branch:
        current_branch = run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
        ).strip()
        run_git(["push", remote, current_branch])
    if push_tag and tag_name:
        run_git(["push", remote, tag_name])


@dataclass
class ReleaseConfig:
    """Normalized configuration for executing a release."""

    version: str
    prerelease: bool
    base_version: str | None
    rc_number: int | None
    manifest_paths: list[Path]
    notes: str
    notes_source: str
    dry_run: bool
    create_commit: bool
    create_tag: bool
    push_branch: bool
    push_tag: bool
    create_github_release: bool
    remote: str
    commit_message: str
    previous_tag: str | None


def check_git_status_interactive() -> None:
    """Warn about dirty worktree and allow the user to continue or abort."""
    status = run_git(["status", "--porcelain"], capture_output=True)
    if status.strip():
        print("⚠️  Uncommitted changes detected:\n")
        print(status.rstrip())
        response = prompt_input("\nContinue anyway? (y/N): ").strip().lower()
        if response != "y":
            raise ReleaseError("Aborted by user.")


def collect_recent_commits(previous_tag: str | None) -> str:
    """Return a shortlog of commits since previous_tag."""
    if previous_tag:
        return run_git(
            ["log", f"{previous_tag}..HEAD", "--oneline"],
            capture_output=True,
        ).strip()
    return run_git(["log", "--oneline", "-10"], capture_output=True).strip()


def prompt_input(message: str) -> str:
    """Read input from stdin and raise ReleaseError on cancellation."""
    try:
        return input(message)
    except EOFError as exc:
        raise ReleaseError("Input cancelled.") from exc
    except KeyboardInterrupt as exc:
        raise ReleaseError("Aborted by user.") from exc


def build_interactive_config() -> ReleaseConfig:
    """Build a ReleaseConfig via the interactive flow inspired by grinder tool."""
    print("=== Marstek Local API Release Helper ===\n")

    check_git_status_interactive()

    manifest_paths = load_manifest_paths(None)
    manifest_list = ", ".join(str(path.relative_to(REPO_ROOT)) for path in manifest_paths)
    current_manifest_version = detect_current_manifest_version()

    previous_tag = get_latest_tag()
    current_tag_display = previous_tag or "v0.0.0"

    print(f"Detected manifest(s): {manifest_list}")
    if current_manifest_version:
        print(f"Current manifest version: {current_manifest_version}")
    print(f"Latest git tag: {current_tag_display}")

    commits = collect_recent_commits(previous_tag)
    if commits:
        print("\nRecent commits since last tag:")
        print(commits)
    else:
        print("\nNo new commits since last tag.")
        response = prompt_input("Continue anyway? (y/N): ").strip().lower()
        if response != "y":
            raise ReleaseError("Aborted by user.")

    tag_version = current_tag_display.lstrip("v")
    if tag_version == "0.0.0":
        # No real release yet
        tag_is_rc = False
        base_version = "0.0.0"
    else:
        tag_is_rc = is_rc_version(tag_version)
        base_version = strip_rc_suffix(tag_version) or "0.0.0"

    # Compute candidate versions
    patch_base = increment_base_version(base_version, "patch")
    minor_base = increment_base_version(base_version, "minor")
    major_base = increment_base_version(base_version, "major")

    patch_rc, patch_rc_number = compute_rc_version(patch_base, rc_number=None)
    minor_rc, minor_rc_number = compute_rc_version(minor_base, rc_number=None)
    major_rc, major_rc_number = compute_rc_version(major_base, rc_number=None)

    if tag_is_rc:
        promoted_version = strip_rc_suffix(tag_version)
        assert promoted_version is not None
        continue_rc, continue_rc_number = compute_rc_version(base_version, rc_number=None)
    else:
        promoted_version = None
        continue_rc = minor_rc
        continue_rc_number = minor_rc_number

    print("\nWhat would you like to release?")
    option_map: dict[str, dict[str, str | int | None]] = {}

    if tag_is_rc and promoted_version:
        print(f"0. Promote RC to stable: v{tag_version} → v{promoted_version}")
        option_map["0"] = {
            "version": promoted_version,
            "command": "final",
            "rc_number": None,
            "base_version": None,
        }

    print(f"1. Patch RC (bug fixes): v{tag_version} → v{patch_rc}")
    option_map["1"] = {
        "version": patch_rc,
        "command": "rc",
        "rc_number": patch_rc_number,
        "base_version": patch_base,
    }

    print(f"2. Minor RC (features): v{tag_version} → v{minor_rc}")
    option_map["2"] = {
        "version": minor_rc,
        "command": "rc",
        "rc_number": minor_rc_number,
        "base_version": minor_base,
    }

    print(f"3. Major RC (breaking changes): v{tag_version} → v{major_rc}")
    option_map["3"] = {
        "version": major_rc,
        "command": "rc",
        "rc_number": major_rc_number,
        "base_version": major_base,
    }

    if tag_is_rc:
        print(f"4. Continue RC testing: v{tag_version} → v{continue_rc}")
    else:
        print(f"4. Start RC cycle: v{tag_version} → v{continue_rc}")
    option_map["4"] = {
        "version": continue_rc,
        "command": "rc",
        "rc_number": continue_rc_number,
        "base_version": base_version if tag_is_rc else minor_base,
    }

    print("5. Custom version")
    print("6. Cancel")

    valid_choices = list(option_map.keys()) + ["5", "6"]
    choice = prompt_input(f"\nEnter choice ({', '.join(valid_choices)}): ").strip()

    if choice == "6":
        raise ReleaseError("Aborted by user.")

    if choice == "5":
        custom_version = prompt_input("Enter version (e.g., 1.2.3 or 1.2.3-rc.4): ").strip()
        if custom_version.startswith("v"):
            custom_version = custom_version[1:]
        if is_rc_version(custom_version):
            base_version, rc_number = parse_rc_components(custom_version)
            command = "rc"
        else:
            validate_base_version(custom_version)
            base_version = None
            rc_number = None
            command = "final"
        selected = {
            "version": custom_version,
            "command": command,
            "rc_number": rc_number,
            "base_version": base_version,
        }
    elif choice in option_map:
        selected = option_map[choice]
    else:
        raise ReleaseError("Invalid selection.")

    version = str(selected["version"])
    command = str(selected["command"])
    rc_number = selected["rc_number"]
    base_version_selected = selected["base_version"]

    print(f"\nPreparing release v{version}")
    notes = generate_release_notes(previous_tag)

    print("\n--- Release Preview ---")
    print(f"Version:      v{version}")
    print(f"Manifest(s):  {manifest_list}")
    print("Release Notes:")
    print(notes if notes else "  (none)")
    print("--- End Preview ---\n")

    response = prompt_input(f"Proceed with release v{version}? (y/N): ").strip().lower()
    if response != "y":
        raise ReleaseError("Aborted by user.")

    prerelease = is_rc_version(version)
    if prerelease and base_version_selected is None:
        base_version_selected, rc_number = parse_rc_components(version)

    config = ReleaseConfig(
        version=version,
        prerelease=prerelease,
        base_version=base_version_selected if isinstance(base_version_selected, str) else None,
        rc_number=int(rc_number) if rc_number is not None else None,
        manifest_paths=manifest_paths,
        notes=notes,
        notes_source="auto-generated",
        dry_run=False,
        create_commit=True,
        create_tag=True,
        push_branch=True,
        push_tag=True,
        create_github_release=True,
        remote="origin",
        commit_message=f"Release {version}",
        previous_tag=previous_tag,
    )
    return config


def create_config_from_args(args: argparse.Namespace) -> ReleaseConfig:
    """Translate CLI arguments to a ReleaseConfig."""
    manifest_paths = load_manifest_paths(args.manifest)
    previous_tag = get_latest_tag()

    if args.command == "final":
        version = validate_base_version(args.version)
        prerelease = False
        base_version = None
        rc_number = None
    else:
        base_version = validate_base_version(args.base_version)
        version, rc_number = compute_rc_version(base_version, rc_number=args.rc_number)
        prerelease = True

    notes = read_notes(args, previous_tag)
    notes_source = "provided" if (args.notes or args.notes_file) else "auto-generated"

    config = ReleaseConfig(
        version=version,
        prerelease=prerelease,
        base_version=base_version,
        rc_number=rc_number,
        manifest_paths=manifest_paths,
        notes=notes,
        notes_source=notes_source,
        dry_run=bool(args.dry_run),
        create_commit=not args.skip_commit,
        create_tag=not args.skip_tag,
        push_branch=bool(args.push),
        push_tag=bool(args.push) and not args.skip_tag,
        create_github_release=not args.skip_github,
        remote=args.remote,
        commit_message=args.commit_message or f"Release {version}",
        previous_tag=previous_tag,
    )
    return config


def execute_release(config: ReleaseConfig) -> None:
    """Perform the release according to the supplied configuration."""
    release_tag = f"v{config.version}"
    manifest_rel_paths = [str(path.relative_to(REPO_ROOT)) for path in config.manifest_paths]

    updated_manifests = update_manifest_versions(
        config.manifest_paths,
        new_version=config.version,
        dry_run=config.dry_run,
    )

    if config.create_commit and not config.dry_run:
        run_git(["add", *[str(path.relative_to(REPO_ROOT)) for path in updated_manifests]])
        run_git(["commit", "-m", config.commit_message])
    elif config.create_commit:
        print("[dry-run] Would stage manifest changes and commit.")
    else:
        print("[skip] Not creating release commit.")

    if config.create_tag and not config.dry_run:
        run_git(["tag", "-a", release_tag, "-m", f"Release {config.version}"])
    elif config.create_tag:
        print(f"[dry-run] Would create tag {release_tag}.")
    else:
        print("[skip] Not creating git tag.")

    if config.push_branch or config.push_tag:
        if config.dry_run:
            print("[dry-run] Would push release commit/tag.")
        else:
            push_changes(
                config.remote,
                release_tag,
                push_tag=config.push_tag,
                push_branch=config.push_branch,
            )

    if config.create_github_release:
        if config.dry_run:
            print("[dry-run] Would create GitHub release.")
        else:
            release_name = release_tag
            if config.prerelease and config.base_version and config.rc_number is not None:
                release_name = f"{config.base_version} RC {config.rc_number}"
            create_github_release(
                tag_name=release_tag,
                release_name=release_name,
                body=config.notes,
                prerelease=config.prerelease,
                remote=config.remote,
            )
    else:
        print("[skip] Not creating GitHub release.")

    print("\nRelease details:")
    print(f"  Version:      {config.version}")
    print(f"  Tag:          {release_tag}")
    print(f"  Type:         {'Release Candidate' if config.prerelease else 'Final Release'}")
    if config.rc_number:
        print(f"  RC number:    {config.rc_number}")
    if config.base_version:
        print(f"  Base version: {config.base_version}")
    print(f"  Notes source: {config.notes_source}")
    print(f"  Manifests:    {', '.join(manifest_rel_paths)}")


def detect_current_manifest_version() -> str | None:
    """Return the version currently stored in the first manifest, if any."""
    for manifest in sorted(REPO_ROOT.glob(DEFAULT_MANIFEST_GLOB)):
        try:
            data = json.loads(manifest.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        version = data.get("version")
        if isinstance(version, str) and version:
            return version
    return None


def strip_rc_suffix(version: str | None) -> str | None:
    """Return version without any -rc.* suffix."""
    if not version:
        return None
    match = re.match(r"(\d+\.\d+\.\d+)", version)
    if match:
        return match.group(1)
    return version


def increment_base_version(version: str, increment: str) -> str:
    """Increment a semantic version string (without rc suffix)."""
    validate_base_version(version)
    major, minor, patch = map(int, version.split("."))

    if increment == "major":
        major += 1
        minor = 0
        patch = 0
    elif increment == "minor":
        minor += 1
        patch = 0
    elif increment == "patch":
        patch += 1
    else:
        raise ReleaseError(f"Unknown increment type '{increment}'.")
    return f"{major}.{minor}.{patch}"


RC_VERSION_REGEX = re.compile(r"^(\d+\.\d+\.\d+)\.rc(\d+)$")


def is_rc_version(version: str) -> bool:
    """Return True if version string denotes a release candidate."""
    return bool(RC_VERSION_REGEX.fullmatch(version))


def parse_rc_components(version: str) -> tuple[str, int]:
    """Extract base version and RC number from an RC version string."""
    match = RC_VERSION_REGEX.fullmatch(version)
    if not match:
        raise ReleaseError(f"Invalid RC version: {version}")
    base_version = match.group(1)
    rc_number = int(match.group(2))
    return base_version, rc_number


def main(argv: list[str] | None = None) -> None:
    os.chdir(REPO_ROOT)

    parser = build_parser()
    argv_list = list(sys.argv[1:] if argv is None else argv)
    if not argv_list:
        config = build_interactive_config()
        execute_release(config)
        return

    args = parser.parse_args(argv_list)

    ensure_clean_worktree()

    config = create_config_from_args(args)
    execute_release(config)


if __name__ == "__main__":
    try:
        main()
    except ReleaseError as err:
        print(f"error: {err}", file=sys.stderr)
        sys.exit(1)
