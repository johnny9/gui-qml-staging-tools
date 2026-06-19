#!/usr/bin/env python3
"""Rewrite a gui-qml branch into the staging-tree path layout.

The normal workflow is to run this from the gui-qml-qt6 checkout after adding
provenance trailers:

    ../gui-qml-maintainer-tools/filter_branch_for_staging.py \
        --switch

The path filter keeps only the QML application and tests:

    qml/             -> src/qml/
    test/functional/ -> test/functional/
    test/*           -> src/qml/test/*

All other paths are dropped. Commits whose filtered tree is unchanged from their
single surviving parent are pruned.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path


DEFAULT_SOURCE_REF = "qt6-main-provenance-trailers"
DEFAULT_BRANCH = "qt6-src-qml-on-staging"
DEFAULT_BASE_REF = "refs/heads/fork/staging"
DEFAULT_TRUST_SOURCE_PROVENANCE = True
PR_IN_MERGE_SUBJECT_RE = re.compile(r"^Merge (bitcoin-core/gui-qml#[0-9]+)(?::|$)")
TRAILER_RE = re.compile(r"^([A-Za-z0-9-]+):\s*(.*)$")


class ScriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class CommitData:
    parents: tuple[str, ...]
    author_name: str
    author_email: str
    author_date: str
    committer_name: str
    committer_email: str
    committer_date: str
    message: str


@dataclass(frozen=True)
class RewriteInput:
    commit: str
    force_keep: bool = False
    source: str = "history"
    pr_id: str | None = None
    merge_commit: str | None = None
    merge_parents: tuple[str, ...] = ()


@dataclass(frozen=True)
class FirstParentCommit:
    commit: str
    parents: tuple[str, ...]
    subject: str


@dataclass
class FilterStats:
    kept_entries: int = 0
    dropped_entries: int = 0
    path_kinds: Counter[str] | None = None

    def __post_init__(self) -> None:
        if self.path_kinds is None:
            self.path_kinds = Counter()


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    input_data: str | bytes | None = None,
    env: dict[str, str] | None = None,
    text: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        input=input_data,
        text=text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if check and result.returncode != 0:
        command = " ".join(args)
        where = f" in {cwd}" if cwd else ""
        stdout = result.stdout if isinstance(result.stdout, str) else result.stdout.decode(errors="replace")
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode(errors="replace")
        raise ScriptError(
            f"command failed{where}: {command}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )
    return result


def git(repo: Path, *args: str, input_data: str | None = None, env: dict[str, str] | None = None) -> str:
    result = run(["git", *args], cwd=repo, input_data=input_data, env=env, text=True)
    return result.stdout  # type: ignore[return-value]


def git_bytes(repo: Path, *args: str, input_data: bytes | None = None, env: dict[str, str] | None = None) -> bytes:
    result = run(["git", *args], cwd=repo, input_data=input_data, env=env, text=False)
    return result.stdout  # type: ignore[return-value]


def git_top_level(path: Path) -> Path:
    return Path(git(path, "rev-parse", "--show-toplevel").strip())


def rev_parse(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def status_lines(repo: Path) -> list[str]:
    return git(repo, "status", "--porcelain=v1").splitlines()


def ensure_clean(repo: Path, description: str) -> None:
    status = status_lines(repo)
    if status:
        raise ScriptError(f"{description} is not clean:\n" + "\n".join(status[:80]))


def branch_exists(repo: Path, branch: str) -> bool:
    result = run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=repo, check=False)
    return result.returncode == 0


def current_branch(repo: Path) -> str:
    return git(repo, "branch", "--show-current").strip()


def commit_subject(repo: Path, commit: str) -> str:
    return git(repo, "show", "-s", "--format=%s", commit).strip()


def commit_data(repo: Path, commit: str) -> CommitData:
    raw = git(
        repo,
        "show",
        "-s",
        "--format=%P%x00%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI%x00%B",
        commit,
    )
    parent_line, author_name, author_email, author_date, committer_name, committer_email, committer_date, message = raw.split(
        "\x00", 7
    )
    return CommitData(
        parents=tuple(parent for parent in parent_line.split() if parent),
        author_name=author_name,
        author_email=author_email,
        author_date=author_date,
        committer_name=committer_name,
        committer_email=committer_email,
        committer_date=committer_date,
        message=message,
    )


def first_parent_history(repo: Path, ref: str) -> list[FirstParentCommit]:
    raw = git(repo, "log", "--first-parent", "--reverse", "--format=%H%x00%P%x00%s%x00END%x00", ref)
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
            raise ScriptError("could not parse first-parent history")
        records.append(
            FirstParentCommit(
                commit=commit,
                parents=tuple(parent for parent in parents.split() if parent),
                subject=subject,
            )
        )
    return records


def rewrite_inputs(
    repo: Path,
    source_ref: str,
    *,
    linear_first_parent: bool,
    expand_pr_side_commits: bool,
    drop_pr_merge_boundaries: bool,
) -> list[RewriteInput]:
    if expand_pr_side_commits:
        commits: list[RewriteInput] = []
        emitted: set[str] = set()
        for item in first_parent_history(repo, source_ref):
            match = PR_IN_MERGE_SUBJECT_RE.match(item.subject)
            if match and len(item.parents) == 2:
                pr_id = match.group(1)
                side_commits = git(repo, "rev-list", "--reverse", f"{item.parents[0]}..{item.parents[1]}").splitlines()
                for side_commit in side_commits:
                    if side_commit in emitted:
                        continue
                    commits.append(
                        RewriteInput(
                            side_commit,
                            force_keep=True,
                            source="pr-side",
                            pr_id=pr_id,
                            merge_commit=item.commit,
                            merge_parents=item.parents,
                        )
                    )
                    emitted.add(side_commit)
                if not drop_pr_merge_boundaries and item.commit not in emitted:
                    commits.append(
                        RewriteInput(
                            item.commit,
                            force_keep=True,
                            source="pr-merge",
                            pr_id=pr_id,
                            merge_commit=item.commit,
                            merge_parents=item.parents,
                        )
                    )
                    emitted.add(item.commit)
                continue

            if item.commit not in emitted:
                commits.append(RewriteInput(item.commit, source="first-parent"))
                emitted.add(item.commit)
        return commits

    rev_list_args = ["rev-list", "--reverse"]
    if linear_first_parent:
        rev_list_args.append("--first-parent")
    else:
        rev_list_args.append("--topo-order")
    rev_list_args.append(source_ref)
    return [RewriteInput(commit) for commit in git(repo, *rev_list_args).splitlines()]


def rewrite_path(path: str) -> tuple[str | None, str | None]:
    if path == "qml":
        return "src/qml", "qml"
    if path.startswith("qml/"):
        return "src/qml/" + path[len("qml/") :], "qml"
    if path == "test/functional" or path.startswith("test/functional/"):
        return path, "functional"
    if path == "test":
        return "src/qml/test", "test"
    if path.startswith("test/"):
        return "src/qml/test/" + path[len("test/") :], "test"
    return None, None


def empty_tree(repo: Path) -> str:
    return git(repo, "mktree", input_data="").strip()


def filtered_tree_for_commit(repo: Path, commit: str, stats: FilterStats) -> str:
    raw = git_bytes(repo, "ls-tree", "-rz", commit)
    entries: list[bytes] = []
    seen: dict[str, bytes] = {}

    for record in raw.split(b"\x00"):
        if not record:
            continue
        try:
            metadata, old_path_bytes = record.split(b"\t", 1)
        except ValueError as exc:
            raise ScriptError(f"could not parse ls-tree record for {commit}: {record!r}") from exc
        old_path = old_path_bytes.decode("utf-8", errors="surrogateescape")
        new_path, kind = rewrite_path(old_path)
        if new_path is None:
            stats.dropped_entries += 1
            continue

        new_path_bytes = new_path.encode("utf-8", errors="surrogateescape")
        new_record = metadata + b"\t" + new_path_bytes
        existing = seen.get(new_path)
        if existing:
            if existing != new_record:
                raise ScriptError(f"path collision after rewrite in {commit}: {old_path} -> {new_path}")
            continue
        seen[new_path] = new_record
        entries.append(new_record + b"\x00")
        stats.kept_entries += 1
        assert stats.path_kinds is not None
        stats.path_kinds[kind or "unknown"] += 1

    index_path = Path(git(repo, "rev-parse", "--git-path", f"codex-filter-index-{os.getpid()}").strip())
    lock_path = Path(str(index_path) + ".lock")
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(index_path)
    try:
        git(repo, "read-tree", "--empty", env=env)
        if entries:
            git_bytes(repo, "update-index", "-z", "--index-info", input_data=b"".join(entries), env=env)
        return git(repo, "write-tree", env=env).strip()
    finally:
        index_path.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)


def filtered_import_tree(
    repo: Path,
    commit: str,
    stats: FilterStats,
    *,
    base_ref: str | None,
    owned_paths: set[str],
) -> str:
    tree = filtered_tree_for_commit(repo, commit, stats)
    if base_ref:
        _entries, current_paths = tree_index_entries(repo, tree)
        owned_paths.update(current_paths)
        tree = overlay_tree(repo, base_ref, tree, owned_paths)
    return tree


def tree_index_entries(repo: Path, tree: str) -> tuple[list[bytes], set[str]]:
    raw = git_bytes(repo, "ls-tree", "-rz", "-r", tree)
    entries: list[bytes] = []
    paths: set[str] = set()

    for record in raw.split(b"\x00"):
        if not record:
            continue
        try:
            _metadata, path_bytes = record.split(b"\t", 1)
        except ValueError as exc:
            raise ScriptError(f"could not parse ls-tree record for {tree}: {record!r}") from exc
        paths.add(path_bytes.decode("utf-8", errors="surrogateescape"))
        entries.append(record + b"\x00")
    return entries, paths


def overlay_tree(repo: Path, base_ref: str, filtered_tree: str, owned_paths: set[str]) -> str:
    entries, _paths = tree_index_entries(repo, filtered_tree)
    delete_entries = [
        f"0 0000000000000000000000000000000000000000\t{path}".encode("utf-8", errors="surrogateescape")
        + b"\x00"
        for path in sorted(owned_paths)
    ]

    index_path = Path(git(repo, "rev-parse", "--git-path", f"codex-filter-overlay-index-{os.getpid()}").strip())
    lock_path = Path(str(index_path) + ".lock")
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(index_path)
    try:
        git(repo, "read-tree", base_ref, env=env)
        if delete_entries or entries:
            git_bytes(repo, "update-index", "-z", "--index-info", input_data=b"".join(delete_entries + entries), env=env)
        return git(repo, "write-tree", env=env).strip()
    finally:
        index_path.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)


def filtered_final_paths(repo: Path, commit: str) -> list[str]:
    return git(repo, "ls-tree", "-r", "--name-only", commit).splitlines()


def existing_trailer_value(message: str, key: str) -> str | None:
    prefix = key.lower() + ":"
    values: list[str] = []
    for line in message.splitlines():
        if line.lower().startswith(prefix):
            values.append(line.split(":", 1)[1].strip())
    return values[-1] if values else None


def build_provenance_trailers(
    message: str,
    commit: str,
    *,
    pr_id: str | None = None,
    trust_existing: bool = False,
) -> list[str]:
    if trust_existing:
        rebased_from = existing_trailer_value(message, "Rebased-From") or commit
        github_pull = existing_trailer_value(message, "Github-Pull") or pr_id
    else:
        rebased_from = commit
        github_pull = pr_id

    trailers = [f"Rebased-From={rebased_from}"]
    if github_pull:
        trailers.append(f"Github-Pull={github_pull}")
    return trailers


def strip_provenance_trailers(message: str) -> str:
    lines = message.rstrip("\n").splitlines()
    end = len(lines)
    while end > 0 and not lines[end - 1]:
        end -= 1
    if end == 0:
        return message

    start = end
    saw_trailer = False
    while start > 0:
        line = lines[start - 1]
        if TRAILER_RE.match(line):
            saw_trailer = True
            start -= 1
            continue
        if saw_trailer and line.startswith((" ", "\t")):
            start -= 1
            continue
        break

    if not saw_trailer or (start > 0 and lines[start - 1]):
        return message

    stripped = lines[:start] + lines[end:]
    return "\n".join(stripped).rstrip() + "\n"


def apply_trailers(repo: Path, message: str, trailers: list[str]) -> str:
    args = ["interpret-trailers", "--if-exists=addIfDifferent"]
    for trailer in trailers:
        args.extend(["--trailer", trailer])
    return git(repo, *args, input_data=strip_provenance_trailers(message))


def retitle_pr_merge_boundary(message: str) -> str:
    lines = message.splitlines()
    if not lines:
        return message
    if not PR_IN_MERGE_SUBJECT_RE.match(lines[0]):
        return message
    lines[0] = re.sub(r"^Merge (bitcoin-core/gui-qml#[0-9]+)", r"Apply \1", lines[0], count=1)
    return "\n".join(lines) + ("\n" if message.endswith("\n") else "")


def create_commit(
    repo: Path,
    tree: str,
    parents: list[str],
    data: CommitData,
    *,
    trailers: list[str] | None = None,
) -> str:
    parent_args: list[str] = []
    for parent in parents:
        parent_args.extend(["-p", parent])
    message = apply_trailers(repo, data.message, trailers) if trailers else data.message
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": data.author_name,
            "GIT_AUTHOR_EMAIL": data.author_email,
            "GIT_AUTHOR_DATE": data.author_date,
            "GIT_COMMITTER_NAME": data.committer_name,
            "GIT_COMMITTER_EMAIL": data.committer_email,
            "GIT_COMMITTER_DATE": data.committer_date,
        }
    )
    return git(repo, "commit-tree", tree, *parent_args, input_data=message, env=env).strip()


def tree_of(repo: Path, commit: str, cache: dict[str, str]) -> str:
    if commit not in cache:
        cache[commit] = git(repo, "rev-parse", f"{commit}^{{tree}}").strip()
    return cache[commit]


def rewrite_history(
    repo: Path,
    source_ref: str,
    *,
    prune_empty: bool,
    linear_first_parent: bool,
    expand_pr_side_commits: bool,
    preserve_pr_merges: bool,
    retitle_pr_merge_boundaries: bool,
    drop_pr_merge_boundaries: bool,
    base_ref: str | None,
    trust_source_provenance: bool,
) -> tuple[str, dict[str, str | None], FilterStats, Counter[str]]:
    if preserve_pr_merges:
        return rewrite_history_preserve_pr_merges(
            repo,
            source_ref,
            prune_empty=prune_empty,
            base_ref=base_ref,
            trust_source_provenance=trust_source_provenance,
        )

    commits = rewrite_inputs(
        repo,
        source_ref,
        linear_first_parent=linear_first_parent,
        expand_pr_side_commits=expand_pr_side_commits,
        drop_pr_merge_boundaries=drop_pr_merge_boundaries,
    )
    if not commits:
        raise ScriptError(f"no commits found for {source_ref}")

    empty = empty_tree(repo)
    rewrite: dict[str, str | None] = {}
    new_tree_cache: dict[str, str] = {}
    stats = FilterStats()
    rewrite_stats: Counter[str] = Counter()
    if linear_first_parent:
        rewrite_stats["linear_first_parent_input_commits"] = len(commits)
    if expand_pr_side_commits:
        rewrite_stats["expanded_input_commits"] = len(commits)
        rewrite_stats.update(commit.source for commit in commits)
    last_new_commit: str | None = None
    owned_paths: set[str] = set()
    linear_import = linear_first_parent or expand_pr_side_commits

    for index, input_commit in enumerate(commits, 1):
        old_commit = input_commit.commit
        data = commit_data(repo, old_commit)
        if retitle_pr_merge_boundaries and input_commit.source == "pr-merge":
            data = replace(data, message=retitle_pr_merge_boundary(data.message))
        tree = filtered_import_tree(repo, old_commit, stats, base_ref=base_ref, owned_paths=owned_paths)
        parents: list[str] = []
        if linear_import:
            if last_new_commit:
                parents.append(last_new_commit)
            elif base_ref:
                parents.append(base_ref)
        else:
            for old_parent in data.parents:
                new_parent = rewrite.get(old_parent)
                if new_parent and new_parent not in parents:
                    parents.append(new_parent)
            if not parents and base_ref:
                parents.append(base_ref)

        if prune_empty and not input_commit.force_keep:
            if not parents and tree == empty:
                rewrite[old_commit] = None
                rewrite_stats["pruned"] += 1
                continue
            if len(parents) == 1 and tree == tree_of(repo, parents[0], new_tree_cache):
                rewrite[old_commit] = parents[0]
                rewrite_stats["pruned"] += 1
                continue
            if len(parents) > 1 and all(tree == tree_of(repo, parent, new_tree_cache) for parent in parents):
                rewrite[old_commit] = parents[0]
                rewrite_stats["pruned"] += 1
                continue

        trailers = build_provenance_trailers(
            data.message,
            old_commit,
            pr_id=input_commit.pr_id,
            trust_existing=trust_source_provenance,
        )
        new_commit = create_commit(repo, tree, parents, data, trailers=trailers)
        rewrite[old_commit] = new_commit
        new_tree_cache[new_commit] = tree
        last_new_commit = new_commit
        rewrite_stats["rewritten"] += 1
        if input_commit.force_keep:
            rewrite_stats["force_kept"] += 1
        if len(parents) > 1:
            rewrite_stats["merge_commits"] += 1

        if index % 200 == 0 or index == len(commits):
            print(f"processed {index}/{len(commits)}")

    new_head = rewrite.get(source_ref) or last_new_commit
    if not new_head:
        raise ScriptError("path filter removed the source ref")
    return new_head, rewrite, stats, rewrite_stats


def rewrite_history_preserve_pr_merges(
    repo: Path,
    source_ref: str,
    *,
    prune_empty: bool,
    base_ref: str | None,
    trust_source_provenance: bool,
) -> tuple[str, dict[str, str | None], FilterStats, Counter[str]]:
    first_parent_commits = first_parent_history(repo, source_ref)
    if not first_parent_commits:
        raise ScriptError(f"no commits found for {source_ref}")

    empty = empty_tree(repo)
    rewrite: dict[str, str | None] = {}
    new_tree_cache: dict[str, str] = {}
    stats = FilterStats()
    rewrite_stats: Counter[str] = Counter()
    rewrite_stats["first_parent_input_commits"] = len(first_parent_commits)
    owned_paths: set[str] = set()
    last_new_commit: str | None = None
    emitted_side_commits: set[str] = set()

    for index, item in enumerate(first_parent_commits, 1):
        data = commit_data(repo, item.commit)
        match = PR_IN_MERGE_SUBJECT_RE.match(item.subject)

        if match and len(item.parents) == 2:
            main_parent = last_new_commit or base_ref
            side_tip = main_parent
            side_commits = git(repo, "rev-list", "--reverse", f"{item.parents[0]}..{item.parents[1]}").splitlines()

            for side_commit in side_commits:
                existing_side = rewrite.get(side_commit)
                if side_commit in emitted_side_commits:
                    if existing_side:
                        side_tip = existing_side
                    continue

                side_data = commit_data(repo, side_commit)
                side_tree = filtered_import_tree(repo, side_commit, stats, base_ref=base_ref, owned_paths=owned_paths)
                side_parents = [side_tip] if side_tip else []
                side_trailers = build_provenance_trailers(
                    side_data.message,
                    side_commit,
                    pr_id=match.group(1),
                    trust_existing=trust_source_provenance,
                )
                new_side = create_commit(repo, side_tree, side_parents, side_data, trailers=side_trailers)
                rewrite[side_commit] = new_side
                new_tree_cache[new_side] = side_tree
                side_tip = new_side
                emitted_side_commits.add(side_commit)
                rewrite_stats["rewritten"] += 1
                rewrite_stats["pr_side_commits"] += 1

            merge_tree = filtered_import_tree(repo, item.commit, stats, base_ref=base_ref, owned_paths=owned_paths)
            merge_parents: list[str] = []
            if main_parent:
                merge_parents.append(main_parent)
            if side_tip and side_tip != main_parent:
                merge_parents.append(side_tip)
            merge_trailers = build_provenance_trailers(
                data.message,
                item.commit,
                pr_id=match.group(1),
                trust_existing=trust_source_provenance,
            )
            new_merge = create_commit(repo, merge_tree, merge_parents, data, trailers=merge_trailers)
            rewrite[item.commit] = new_merge
            new_tree_cache[new_merge] = merge_tree
            last_new_commit = new_merge
            rewrite_stats["rewritten"] += 1
            rewrite_stats["pr_merges"] += 1
            if len(merge_parents) > 1:
                rewrite_stats["merge_commits"] += 1

            if index % 50 == 0 or index == len(first_parent_commits):
                print(f"processed {index}/{len(first_parent_commits)}")
            continue

        tree = filtered_import_tree(repo, item.commit, stats, base_ref=base_ref, owned_paths=owned_paths)
        parents: list[str] = []
        if last_new_commit:
            parents.append(last_new_commit)
        elif base_ref:
            parents.append(base_ref)

        if prune_empty:
            if not parents and tree == empty:
                rewrite[item.commit] = None
                rewrite_stats["pruned"] += 1
                continue
            if len(parents) == 1 and tree == tree_of(repo, parents[0], new_tree_cache):
                rewrite[item.commit] = parents[0]
                rewrite_stats["pruned"] += 1
                continue

        trailers = build_provenance_trailers(
            data.message,
            item.commit,
            trust_existing=trust_source_provenance,
        )
        new_commit = create_commit(repo, tree, parents, data, trailers=trailers)
        rewrite[item.commit] = new_commit
        new_tree_cache[new_commit] = tree
        last_new_commit = new_commit
        rewrite_stats["rewritten"] += 1
        rewrite_stats["first_parent_commits"] += 1

        if index % 50 == 0 or index == len(first_parent_commits):
            print(f"processed {index}/{len(first_parent_commits)}")

    new_head = rewrite.get(source_ref)
    if not new_head:
        raise ScriptError("path filter removed the source ref")
    return new_head, rewrite, stats, rewrite_stats


def write_map_file(
    path: Path,
    *,
    old_head: str,
    new_head: str,
    branch: str,
    rewrite: dict[str, str | None],
    filter_stats: FilterStats,
    rewrite_stats: Counter[str],
    unreachable_created: list[str],
) -> None:
    data = {
        "old_head": old_head,
        "new_head": new_head,
        "branch": branch,
        "rewrite_stats": dict(rewrite_stats),
        "filter_stats": {
            "kept_entries": filter_stats.kept_entries,
            "dropped_entries": filter_stats.dropped_entries,
            "path_kinds": dict(filter_stats.path_kinds or {}),
        },
        "unreachable_created": unreachable_created,
        "old_to_new": rewrite,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def validate_paths(paths: list[str]) -> list[str]:
    bad: list[str] = []
    for path in paths:
        if path.startswith("src/qml/") or path == "src/qml":
            continue
        if path.startswith("test/functional/") or path == "test/functional":
            continue
        bad.append(path)
    return bad


def apply_default_history_mode(args: argparse.Namespace) -> None:
    """Default to the full staging import unless another mode was selected."""
    expand_pr_side_commits = getattr(args, "expand_pr_side_commits", False)
    if not (args.linear_first_parent or expand_pr_side_commits or args.preserve_pr_merges):
        args.expand_pr_side_commits = True
    else:
        args.expand_pr_side_commits = expand_pr_side_commits
    drop_pr_merge_boundaries = getattr(args, "drop_pr_merge_boundaries", None)
    args.drop_pr_merge_boundaries = drop_pr_merge_boundaries
    if args.drop_pr_merge_boundaries is None:
        args.drop_pr_merge_boundaries = args.expand_pr_side_commits and not args.retitle_pr_merge_boundaries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a staging-layout branch from gui-qml history.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--repo", default=".", help="repository containing the source branch")
    parser.add_argument("--source-ref", default=DEFAULT_SOURCE_REF, help="source ref to rewrite")
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help="branch to create at the rewritten tip")
    parser.add_argument("--force-branch", action="store_true", help="overwrite --branch if it already exists")
    parser.add_argument("--switch", action="store_true", help="switch the checkout to the new branch")
    parser.add_argument("--keep-empty", action="store_true", help="keep commits that become empty after filtering")
    parser.add_argument(
        "--linear-first-parent",
        action="store_true",
        help="rewrite only source first-parent history as a linear import stream",
    )
    parser.add_argument(
        "--expand-pr-side-commits",
        "--linear-pr-history",
        action="store_true",
        default=argparse.SUPPRESS,
        help=(
            "default when no history mode is selected; rewrite a single-parent "
            "import stream that expands each gui-qml PR merge into its PR-side "
            "commits plus the reviewed merge-result boundary commit, without "
            "recreating merge branches"
        ),
    )
    parser.add_argument(
        "--preserve-pr-merges",
        "--pr-merge-chunks",
        action="store_true",
        help=(
            "rewrite first-parent gui-qml PR merges as real two-parent merge commits; "
            "the recreated merge uses the filtered original merge tree as the resolved result"
        ),
    )
    parser.add_argument(
        "--retitle-pr-merge-boundaries",
        action="store_true",
        help=(
            "with --expand-pr-side-commits/--linear-pr-history, retitle one-parent "
            "PR merge-result boundary commits from 'Merge ...' to 'Apply ...'"
        ),
    )
    parser.add_argument(
        "--drop-pr-merge-boundaries",
        action="store_true",
        default=argparse.SUPPRESS,
        help=(
            "with --expand-pr-side-commits/--linear-pr-history, omit the one-parent "
            "PR merge-result boundary commits entirely"
        ),
    )
    parser.add_argument(
        "--keep-pr-merge-boundaries",
        dest="drop_pr_merge_boundaries",
        action="store_false",
        default=argparse.SUPPRESS,
        help="with --expand-pr-side-commits/--linear-pr-history, keep one-parent PR merge-result boundary commits",
    )
    parser.add_argument(
        "--base-ref",
        default=DEFAULT_BASE_REF,
        help="build rewritten commits on this base tree, preserving paths not owned by the filter",
    )
    parser.add_argument(
        "--no-base-ref",
        dest="base_ref",
        action="store_const",
        const=None,
        default=argparse.SUPPRESS,
        help="build the filtered branch without overlaying it onto a base tree",
    )
    parser.add_argument("--write-map", type=Path, help="write old-to-new rewrite map to this file")
    parser.add_argument(
        "--trust-source-provenance",
        action="store_true",
        default=DEFAULT_TRUST_SOURCE_PROVENANCE,
        help=(
            "reuse existing Github-Pull/Rebased-From trailers from the source ref; "
            "use after add_filter_branch_metadata.py has prepared two-stage provenance"
        ),
    )
    parser.add_argument(
        "--no-trust-source-provenance",
        dest="trust_source_provenance",
        action="store_false",
        default=argparse.SUPPRESS,
        help="ignore existing Github-Pull/Rebased-From trailers on the source ref",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        apply_default_history_mode(args)
        mode_count = sum(
            bool(value)
            for value in (args.linear_first_parent, args.expand_pr_side_commits, args.preserve_pr_merges)
        )
        if mode_count > 1:
            raise ScriptError(
                "--linear-first-parent, --expand-pr-side-commits/--linear-pr-history, "
                "and --preserve-pr-merges are mutually exclusive"
            )
        if args.retitle_pr_merge_boundaries and not args.expand_pr_side_commits:
            raise ScriptError("--retitle-pr-merge-boundaries requires --expand-pr-side-commits/--linear-pr-history")
        if args.drop_pr_merge_boundaries and not args.expand_pr_side_commits:
            raise ScriptError("--drop-pr-merge-boundaries requires --expand-pr-side-commits/--linear-pr-history")
        if args.drop_pr_merge_boundaries and args.retitle_pr_merge_boundaries:
            raise ScriptError("--drop-pr-merge-boundaries and --retitle-pr-merge-boundaries are mutually exclusive")
        repo = git_top_level(Path(args.repo).resolve())
        old_head = rev_parse(repo, args.source_ref)
        base_ref = rev_parse(repo, args.base_ref) if args.base_ref else None
        if args.switch:
            ensure_clean(repo, "repository checkout")
        if branch_exists(repo, args.branch):
            if not args.force_branch:
                raise ScriptError(f"branch already exists: {args.branch}; pass --force-branch to overwrite it")
            if current_branch(repo) == args.branch:
                raise ScriptError(f"cannot force-update checked-out branch: {args.branch}")

        print(f"source: {repo} {old_head}")
        new_head, rewrite, filter_stats, rewrite_stats = rewrite_history(
            repo,
            old_head,
            prune_empty=not args.keep_empty,
            linear_first_parent=args.linear_first_parent,
            expand_pr_side_commits=args.expand_pr_side_commits,
            preserve_pr_merges=args.preserve_pr_merges,
            retitle_pr_merge_boundaries=args.retitle_pr_merge_boundaries,
            drop_pr_merge_boundaries=args.drop_pr_merge_boundaries,
            base_ref=base_ref,
            trust_source_provenance=args.trust_source_provenance,
        )
        branch_args = ["branch"]
        if args.force_branch:
            branch_args.append("-f")
        branch_args.extend([args.branch, new_head])
        git(repo, *branch_args)
        if args.switch:
            git(repo, "switch", args.branch)

        paths = filtered_final_paths(repo, new_head)
        bad_paths = [] if base_ref else validate_paths(paths)
        if bad_paths:
            raise ScriptError("filtered branch contains unexpected paths:\n" + "\n".join(bad_paths[:80]))

        reachable = set(git(repo, "rev-list", new_head).splitlines())
        created = {commit for commit in rewrite.values() if commit}
        unreachable_created = sorted(created - reachable)
        rewrite_stats["reachable"] = len(reachable)
        rewrite_stats["unreachable_created"] = len(unreachable_created)

        if args.write_map:
            write_map_file(
                args.write_map,
                old_head=old_head,
                new_head=new_head,
                branch=args.branch,
                rewrite=rewrite,
                filter_stats=filter_stats,
                rewrite_stats=rewrite_stats,
                unreachable_created=unreachable_created,
            )

        print(f"created branch: {args.branch}")
        print(f"old head: {old_head}")
        print(f"new head: {new_head}")
        print("rewrite stats: " + ", ".join(f"{key}={value}" for key, value in sorted(rewrite_stats.items())))
        print(
            "filter stats: "
            f"kept_entries={filter_stats.kept_entries}, "
            f"dropped_entries={filter_stats.dropped_entries}, "
            f"path_kinds={dict(filter_stats.path_kinds or {})}"
        )
        print(f"final paths: {len(paths)}")
        return 0
    except ScriptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
