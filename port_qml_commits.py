#!/usr/bin/env python3
"""Port reviewed gui-qml commits into a Bitcoin Core staging checkout.

The normal workflow is to run this from the target checkout:

    ../gui-qml-maintainer-tools/port_qml_commits.py bitcoin-core/gui-qml#450

The script resolves gui-qml PR merge commits from the source repository,
replays the individual commits that were reviewed in those PRs, rewrites the
configured source paths into the target paths, and appends provenance trailers
to each generated commit.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SOURCE_REPO = "../gui-qml-main"
DEFAULT_SOURCE_REF = "main"
DEFAULT_DEFAULT_PR_REPO = "bitcoin-core/gui-qml"
DEFAULT_PATH_MAPS = ("src/qml:src/qml", "qml:src/qml")


class ScriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class PathMap:
    source: str
    target: str


@dataclass(frozen=True)
class ReviewContext:
    pr_id: str | None = None
    merge_commit: str | None = None
    merge_parents: tuple[str, ...] = ()


@dataclass(frozen=True)
class PortCommit:
    commit: str
    context: ReviewContext
    selector: str


@dataclass(frozen=True)
class FirstParentCommit:
    commit: str
    parents: tuple[str, ...]
    subject: str


PR_IN_MERGE_SUBJECT_RE = re.compile(r"^Merge ([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]+)(?::|$)")
FULL_PR_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]+$")
SHORT_PR_RE = re.compile(r"^#?[0-9]+$")


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    input_data: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        input=input_data,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        command = " ".join(args)
        where = f" in {cwd}" if cwd else ""
        raise ScriptError(
            f"command failed{where}: {command}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def git(repo: Path, *args: str, input_data: str | None = None, check: bool = True) -> str:
    return run(["git", *args], cwd=repo, input_data=input_data, check=check).stdout


def git_top_level(path: Path) -> Path:
    return Path(git(path, "rev-parse", "--show-toplevel").strip())


def rev_parse(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def commit_subject(repo: Path, commit: str) -> str:
    return git(repo, "show", "-s", "--format=%s", commit).strip()


def commit_message(repo: Path, commit: str) -> str:
    return git(repo, "show", "-s", "--format=%B", commit)


def status_lines(repo: Path) -> list[str]:
    return git(repo, "status", "--porcelain=v1").splitlines()


def ensure_clean(repo: Path, description: str) -> None:
    status = status_lines(repo)
    if status:
        raise ScriptError(f"{description} is not clean:\n" + "\n".join(status[:80]))


def parse_path_map(value: str) -> PathMap:
    if ":" not in value:
        raise argparse.ArgumentTypeError("path maps must use SOURCE:TARGET, for example src/qml:src/qml")
    source, target = value.split(":", 1)
    source = source.strip().strip("/")
    target = target.strip().strip("/")
    if not source or not target:
        raise argparse.ArgumentTypeError("path map source and target must both be non-empty")
    return PathMap(source=source, target=target)


def normalize_pr_id(value: str, default_pr_repo: str) -> str | None:
    if FULL_PR_RE.match(value):
        return value
    if SHORT_PR_RE.match(value):
        return f"{default_pr_repo}#{value.lstrip('#')}"
    return None


def parent_hashes(repo: Path, commit: str) -> list[str]:
    parts = git(repo, "rev-list", "--parents", "-n", "1", commit).strip().split()
    if not parts:
        raise ScriptError(f"could not resolve commit parents: {commit}")
    return parts[1:]


def introduced_commits_for_merge(repo: Path, merge_commit: str) -> list[str]:
    parents = parent_hashes(repo, merge_commit)
    if len(parents) != 2:
        raise ScriptError(
            f"PR merge {merge_commit} has {len(parents)} parents; expected a two-parent maintainer merge"
        )
    return git(repo, "rev-list", "--reverse", f"{parents[0]}..{parents[1]}").splitlines()


def first_parent_history(repo: Path, source_ref: str) -> list[FirstParentCommit]:
    raw = git(repo, "log", "--first-parent", "--reverse", "--format=%H%x00%P%x00%s%x00END%x00", source_ref)
    fields = raw.split("\x00")
    records: list[FirstParentCommit] = []
    for index in range(0, len(fields) - 1, 4):
        commit, parents, subject, marker = fields[index : index + 4]
        commit = commit.strip()
        parents = parents.strip()
        marker = marker.strip()
        if not commit:
            continue
        if marker != "END":
            raise ScriptError("could not parse first-parent source history")
        records.append(
            FirstParentCommit(
                commit=commit,
                parents=tuple(parent for parent in parents.split() if parent),
                subject=subject,
            )
        )
    return records


def resolve_prs(
    repo: Path,
    source_ref: str,
    requested_prs: set[str],
) -> list[PortCommit]:
    remaining = set(requested_prs)
    resolved: list[PortCommit] = []
    seen_commits: set[str] = set()

    for source_commit in first_parent_history(repo, source_ref):
        match = PR_IN_MERGE_SUBJECT_RE.match(source_commit.subject)
        if not match:
            continue
        pr_id = match.group(1)
        if pr_id not in remaining:
            continue
        parents = source_commit.parents
        context = ReviewContext(pr_id=pr_id, merge_commit=source_commit.commit, merge_parents=parents)
        for commit in introduced_commits_for_merge(repo, source_commit.commit):
            if commit in seen_commits:
                continue
            resolved.append(PortCommit(commit=commit, context=context, selector=pr_id))
            seen_commits.add(commit)
        remaining.remove(pr_id)

    if remaining:
        raise ScriptError("could not find PR merge(s) on first-parent history: " + ", ".join(sorted(remaining)))
    return resolved


def resolve_commit_or_range(repo: Path, selector: str) -> list[PortCommit]:
    context = ReviewContext()
    if ".." in selector:
        if "..." in selector:
            raise ScriptError(f"use a two-dot range for replay, not three dots: {selector}")
        commits = git(repo, "rev-list", "--reverse", selector).splitlines()
        return [PortCommit(commit=commit, context=context, selector=selector) for commit in commits]
    return [PortCommit(commit=rev_parse(repo, selector), context=context, selector=selector)]


def resolve_selectors(
    repo: Path,
    source_ref: str,
    selectors: list[str],
    default_pr_repo: str,
) -> list[PortCommit]:
    pr_selectors: list[str] = []
    other_selectors: list[str] = []
    for selector in selectors:
        pr_id = normalize_pr_id(selector, default_pr_repo)
        if pr_id:
            pr_selectors.append(pr_id)
        else:
            other_selectors.append(selector)

    resolved: list[PortCommit] = []
    if pr_selectors:
        resolved.extend(resolve_prs(repo, source_ref, set(pr_selectors)))
    for selector in other_selectors:
        resolved.extend(resolve_commit_or_range(repo, selector))
    return resolved


def path_is_mapped(path: str, path_maps: list[PathMap]) -> bool:
    return any(path == mapping.source or path.startswith(mapping.source + "/") for mapping in path_maps)


def source_paths(path_maps: list[PathMap]) -> list[str]:
    paths: list[str] = []
    for mapping in path_maps:
        if mapping.source not in paths:
            paths.append(mapping.source)
    return paths


def target_paths(path_maps: list[PathMap]) -> list[str]:
    paths: list[str] = []
    for mapping in path_maps:
        if mapping.target not in paths:
            paths.append(mapping.target)
    return paths


def changed_files(repo: Path, commit: str) -> list[str]:
    return git(repo, "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", commit).splitlines()


def rewrite_token(token: str, path_maps: list[PathMap]) -> str:
    for mapping in path_maps:
        for prefix in ("a/", "b/"):
            source = prefix + mapping.source
            target = prefix + mapping.target
            if token == source or token.startswith(source + "/"):
                return target + token[len(source) :]
        if token == mapping.source or token.startswith(mapping.source + "/"):
            return mapping.target + token[len(mapping.source) :]
    return token


def rewrite_path_list_line(line: str, path_maps: list[PathMap]) -> str:
    if not line.startswith(" ") or "|" not in line:
        return line
    before, sep, after = line.partition("|")
    path = before.strip()
    if not path:
        return line
    rewritten = rewrite_token(path, path_maps)
    if rewritten == path:
        return line
    padding = " " * max(1, len(before) - len(before.lstrip()))
    return f"{padding}{rewritten} {sep}{after}"


def rewrite_patch_paths(mbox: str, path_maps: list[PathMap]) -> str:
    rewritten_lines: list[str] = []
    for line in mbox.splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line

        if body.startswith("diff --git "):
            parts = body.split(" ")
            if len(parts) >= 4:
                parts[2] = rewrite_token(parts[2], path_maps)
                parts[3] = rewrite_token(parts[3], path_maps)
                rewritten_lines.append(" ".join(parts) + newline)
                continue

        rewritten = False
        for prefix in ("--- ", "+++ "):
            if body.startswith(prefix):
                token = body[len(prefix) :]
                path, sep, suffix = token.partition("\t")
                rewritten_lines.append(prefix + rewrite_token(path, path_maps) + sep + suffix + newline)
                rewritten = True
                break
        if rewritten:
            continue

        for prefix in ("rename from ", "rename to ", "copy from ", "copy to "):
            if body.startswith(prefix):
                rewritten_lines.append(prefix + rewrite_token(body[len(prefix) :], path_maps) + newline)
                rewritten = True
                break
        if rewritten:
            continue

        if body.startswith("Binary files "):
            binary_line = body
            for mapping in path_maps:
                binary_line = binary_line.replace(f"a/{mapping.source}/", f"a/{mapping.target}/")
                binary_line = binary_line.replace(f"b/{mapping.source}/", f"b/{mapping.target}/")
            rewritten_lines.append(binary_line + newline)
        else:
            rewritten_lines.append(rewrite_path_list_line(line, path_maps))

    return "".join(rewritten_lines)


def format_patch(repo: Path, commit: str, path_maps: list[PathMap]) -> str:
    return git(
        repo,
        "format-patch",
        "--stdout",
        "--binary",
        "--full-index",
        "-1",
        commit,
        "--",
        *source_paths(path_maps),
    )


def path_map_trailers(path_maps: list[PathMap]) -> list[str]:
    values: list[str] = []
    for mapping in path_maps:
        value = f"{mapping.source}/={mapping.target}/"
        if value not in values:
            values.append(value)
    return values


def build_trailers(item: PortCommit, commit: str, path_maps: list[PathMap], partial_replay: bool) -> list[str]:
    trailers = [
        f"Original-gui-qml-commit={commit}",
        f"Rebased-From={commit}",
    ]
    if item.context.pr_id:
        trailers.extend(
            [
                f"Original-gui-qml-PR={item.context.pr_id}",
                f"Github-Pull={item.context.pr_id}",
            ]
        )
    if item.context.merge_commit:
        trailers.append(f"Original-gui-qml-merge={item.context.merge_commit}")
    if item.context.merge_parents:
        trailers.append(f"Original-gui-qml-merge-parents={' '.join(item.context.merge_parents)}")
    for value in path_map_trailers(path_maps):
        trailers.append(f"Path-map={value}")
    if partial_replay:
        trailers.append("Ported-subset=path-limited")
    return trailers


def append_trailers(
    target_repo: Path,
    trailers: list[str],
    *,
    gpg_sign: str | None,
) -> None:
    message = commit_message(target_repo, "HEAD")
    args = ["interpret-trailers", "--if-exists=addIfDifferent"]
    for trailer in trailers:
        args.extend(["--trailer", trailer])
    updated = git(target_repo, *args, input_data=message)

    commit_args = ["commit", "--amend", "-q", "-F", "-"]
    if gpg_sign is not None:
        commit_args.append("--gpg-sign" if not gpg_sign else f"--gpg-sign={gpg_sign}")
    git(target_repo, *commit_args, input_data=updated)


def apply_port_commit(
    source_repo: Path,
    target_repo: Path,
    item: PortCommit,
    path_maps: list[PathMap],
    *,
    committer_date_is_author_date: bool,
    gpg_sign: str | None,
    dry_run: bool,
) -> bool:
    commit = rev_parse(source_repo, item.commit)
    parents = parent_hashes(source_repo, commit)
    if len(parents) > 1:
        raise ScriptError(
            f"refusing to replay merge commit directly: {commit} {commit_subject(source_repo, commit)!r}; "
            "select the PR id so the reviewed side commits can be replayed instead"
        )

    all_files = changed_files(source_repo, commit)
    mapped_files = [path for path in all_files if path_is_mapped(path, path_maps)]
    if not mapped_files:
        print(f"skip {commit[:12]}: no files matched path maps ({commit_subject(source_repo, commit)})")
        return False

    partial_replay = len(mapped_files) != len(all_files)
    context = f" {item.context.pr_id}" if item.context.pr_id else ""
    partial = " [path-limited]" if partial_replay else ""
    print(f"{'would port' if dry_run else 'port'}{context} {commit[:12]} {commit_subject(source_repo, commit)}{partial}")

    if dry_run:
        return True

    patch = rewrite_patch_paths(format_patch(source_repo, commit, path_maps), path_maps)
    command = ["am", "--3way", "--whitespace=nowarn"]
    if committer_date_is_author_date:
        command.append("--committer-date-is-author-date")
    try:
        git(target_repo, *command, input_data=patch)
    except ScriptError as exc:
        trailers = build_trailers(item, commit, path_maps, partial_replay)
        print(
            "\nThe patch did not apply cleanly. The target checkout has been left in git-am state.",
            file=sys.stderr,
        )
        print("Resolve conflicts, run `git am --continue`, then amend these trailers:", file=sys.stderr)
        for trailer in trailers:
            key, _, value = trailer.partition("=")
            print(f"  {key}: {value}", file=sys.stderr)
        raise exc

    append_trailers(
        target_repo,
        build_trailers(item, commit, path_maps, partial_replay),
        gpg_sign=gpg_sign,
    )
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Port gui-qml commits or reviewed PRs into a staging checkout with provenance trailers.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "selectors",
        nargs="+",
        help="PR ids, commit ids, or commit ranges to port; PRs may be full ids or numbers",
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE_REPO, help="source gui-qml repository")
    parser.add_argument("--source-ref", default=DEFAULT_SOURCE_REF, help="source ref used to find PR merges")
    parser.add_argument("--target", default=".", help="target staging repository")
    parser.add_argument(
        "--default-pr-repo",
        default=DEFAULT_DEFAULT_PR_REPO,
        help="repo prefix used when a selector is only a PR number",
    )
    parser.add_argument(
        "--path-map",
        action="append",
        type=parse_path_map,
        help="source-to-target path map; repeat to map multiple roots",
    )
    parser.add_argument(
        "--committer-date-is-author-date",
        action="store_true",
        help="pass --committer-date-is-author-date to git am",
    )
    parser.add_argument(
        "--gpg-sign",
        nargs="?",
        const="",
        default=None,
        metavar="KEY",
        help="GPG-sign amended commits, optionally with KEY",
    )
    parser.add_argument("--dry-run", action="store_true", help="resolve and print commits without modifying target")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        source_repo = git_top_level(Path(args.source).resolve())
        target_repo = git_top_level(Path(args.target).resolve())
        source_ref = rev_parse(source_repo, args.source_ref)
        path_maps = args.path_map or [parse_path_map(value) for value in DEFAULT_PATH_MAPS]

        items = resolve_selectors(source_repo, source_ref, args.selectors, args.default_pr_repo)
        if not items:
            raise ScriptError("no commits selected")

        if not args.dry_run:
            ensure_clean(target_repo, "target checkout")

        applied = 0
        for item in items:
            if apply_port_commit(
                source_repo,
                target_repo,
                item,
                path_maps,
                committer_date_is_author_date=args.committer_date_is_author_date,
                gpg_sign=args.gpg_sign,
                dry_run=args.dry_run,
            ):
                applied += 1

        action = "would port" if args.dry_run else "ported"
        print(f"{action} {applied} commit(s)")
        return 0
    except ScriptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
