#!/usr/bin/env python3
"""Add provenance trailers to commits copied from a filtered gui-qml branch.

The normal workflow is to run this from the target checkout:

    ../gui-qml-maintainer-tools/add_filter_branch_metadata.py --switch

The script matches commits in the filtered target history back to commits in the
source history using stable patch-ids after applying the configured path maps.
It then creates a new branch with the same trees and topology as the target ref,
but with Github-Pull and Rebased-From trailers appended to the matched commits.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SOURCE_REPO = "."
DEFAULT_SOURCE_REF = "origin/main"
DEFAULT_TARGET_REF = "origin/qt6"
DEFAULT_TARGET_IMPORT_TIP = "39eb251ad740271bf10820920275e90f219a0290"
DEFAULT_TAG_TARGET_DESCENDANTS = True
DEFAULT_BRANCH = "qt6-main-provenance-trailers"
DEFAULT_PATH_MAPS = ("src/qml:qml", "qml:qml")
PR_IN_MERGE_SUBJECT_RE = re.compile(r"^Merge ([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[0-9]+)(?::|$)")


class ScriptError(RuntimeError):
    pass


@dataclass(frozen=True)
class PathMap:
    source: str
    target: str


@dataclass(frozen=True)
class FirstParentCommit:
    commit: str
    parents: tuple[str, ...]
    subject: str


@dataclass(frozen=True)
class TrailerPair:
    github_pull: str | None
    rebased_from: str


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    input_data: str | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        input=input_data,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
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


def git(repo: Path, *args: str, input_data: str | None = None, env: dict[str, str] | None = None) -> str:
    return run(["git", *args], cwd=repo, input_data=input_data, env=env).stdout


def git_top_level(path: Path) -> Path:
    return Path(git(path, "rev-parse", "--show-toplevel").strip())


def rev_parse(repo: Path, ref: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def commit_subject(repo: Path, commit: str) -> str:
    return git(repo, "show", "-s", "--format=%s", commit).strip()


def status_lines(repo: Path) -> list[str]:
    return git(repo, "status", "--porcelain=v1").splitlines()


def ensure_clean(repo: Path, description: str) -> None:
    status = status_lines(repo)
    if status:
        raise ScriptError(f"{description} is not clean:\n" + "\n".join(status[:80]))


def branch_exists(repo: Path, branch: str) -> bool:
    result = run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=repo, check=False)
    return result.returncode == 0


def parse_path_map(value: str) -> PathMap:
    if ":" not in value:
        raise argparse.ArgumentTypeError("path maps must use SOURCE:TARGET, for example src/qml:qml")
    source, target = value.split(":", 1)
    source = source.strip().strip("/")
    target = target.strip().strip("/")
    if not source or not target:
        raise argparse.ArgumentTypeError("path map source and target must both be non-empty")
    return PathMap(source=source, target=target)


def source_paths(path_maps: list[PathMap]) -> list[str]:
    paths: list[str] = []
    for mapping in path_maps:
        if mapping.source not in paths:
            paths.append(mapping.source)
    return paths


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


def rewrite_patch_paths(patch: str, path_maps: list[PathMap]) -> str:
    """Rewrite only diff metadata paths, not patch body text."""
    rewritten_lines: list[str] = []
    for line in patch.splitlines(keepends=True):
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
            rewritten_lines.append(line)

    return "".join(rewritten_lines)


def patch_id(repo: Path, commit: str, path_maps: list[PathMap], *, is_source: bool) -> str | None:
    args = ["show", "--format=", "--full-index", "--binary", "-M", commit]
    if is_source:
        args.extend(["--", *source_paths(path_maps)])
    patch = git(repo, *args)
    if is_source:
        patch = rewrite_patch_paths(patch, path_maps)
    if not patch.strip():
        return None
    result = run(["git", "patch-id", "--stable"], input_data=patch)
    line = result.stdout.strip()
    return line.split()[0] if line else None


def parent_hashes(repo: Path, commit: str) -> list[str]:
    parts = git(repo, "rev-list", "--parents", "-n", "1", commit).strip().split()
    if not parts:
        raise ScriptError(f"could not resolve commit parents: {commit}")
    return parts[1:]


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


def pr_context_from_first_parent(repo: Path, ref: str) -> tuple[dict[str, str], dict[str, str]]:
    pr_by_commit: dict[str, str] = {}
    merge_by_pr: dict[str, str] = {}
    for item in first_parent_history(repo, ref):
        match = PR_IN_MERGE_SUBJECT_RE.match(item.subject)
        if not match:
            continue
        pr_id = match.group(1)
        pr_by_commit[item.commit] = pr_id
        merge_by_pr[pr_id] = item.commit
        if len(item.parents) != 2:
            continue
        for commit in git(repo, "rev-list", "--reverse", f"{item.parents[0]}..{item.parents[1]}").splitlines():
            pr_by_commit.setdefault(commit, pr_id)
    return pr_by_commit, merge_by_pr


def find_target_import_tip(target_repo: Path, target_ref: str, source_repo: Path, source_ref: str) -> str:
    source_subject = commit_subject(source_repo, source_ref)
    raw = git(target_repo, "log", "--format=%H%x00%s%x00END%x00", target_ref)
    fields = raw.split("\x00")
    matches: list[str] = []
    for index in range(0, len(fields) - 1, 3):
        commit, subject, marker = fields[index : index + 3]
        if not commit.strip():
            continue
        if marker.strip() != "END":
            raise ScriptError("could not parse target log")
        if subject == source_subject:
            matches.append(commit)
    if not matches:
        raise ScriptError(
            f"could not find a commit in target ref with source tip subject {source_subject!r}; "
            "pass --target-import-tip"
        )
    if len(matches) > 1:
        raise ScriptError(
            f"found multiple target commits with source tip subject {source_subject!r}: "
            + ", ".join(matches)
            + "; pass --target-import-tip"
        )
    return matches[0]


def source_candidates(
    source_repo: Path,
    source_ref: str,
    path_maps: list[PathMap],
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, str], dict[str, int]]:
    commits = git(
        source_repo,
        "rev-list",
        "--full-history",
        "--reverse",
        "--topo-order",
        "--no-merges",
        source_ref,
        "--",
        *source_paths(path_maps),
    ).splitlines()
    source_order = {commit: index for index, commit in enumerate(commits)}
    by_patch: dict[str, list[str]] = defaultdict(list)
    by_subject: dict[str, list[str]] = defaultdict(list)
    subjects: dict[str, str] = {}

    for commit in commits:
        subject = commit_subject(source_repo, commit)
        subjects[commit] = subject
        by_subject[subject].append(commit)
        commit_patch_id = patch_id(source_repo, commit, path_maps, is_source=True)
        if commit_patch_id:
            by_patch[commit_patch_id].append(commit)

    for table in (by_patch, by_subject):
        for key in list(table):
            table[key].sort(key=lambda commit: source_order[commit])

    return by_patch, by_subject, subjects, source_order


def build_trailer_map(
    *,
    source_repo: Path,
    source_ref: str,
    target_repo: Path,
    target_import_tip: str,
    path_maps: list[PathMap],
    allow_subject_fallback: bool,
    allow_ordered_duplicates: bool,
) -> tuple[dict[str, TrailerPair], Counter[str], list[tuple[str, str, str, list[str], str | None]]]:
    source_pr_by_commit, source_merge_by_pr = pr_context_from_first_parent(source_repo, source_ref)
    target_pr_by_commit, _ = pr_context_from_first_parent(target_repo, target_import_tip)
    source_by_patch, source_by_subject, source_subjects, source_order = source_candidates(source_repo, source_ref, path_maps)

    trailer_map: dict[str, TrailerPair] = {}
    issues: list[tuple[str, str, str, list[str], str | None]] = []
    match_kinds: Counter[str] = Counter()
    used_source: set[str] = set()

    target_commits = git(target_repo, "rev-list", "--reverse", "--topo-order", target_import_tip).splitlines()
    for commit in target_commits:
        subject = commit_subject(target_repo, commit)
        parents = parent_hashes(target_repo, commit)

        if len(parents) > 1:
            match = PR_IN_MERGE_SUBJECT_RE.match(subject)
            if not match:
                issues.append((commit, subject, "merge without PR subject", [], None))
                continue
            pr_id = match.group(1)
            source_merge = source_merge_by_pr.get(pr_id)
            if not source_merge:
                issues.append((commit, subject, f"missing source merge for {pr_id}", [], pr_id))
                continue
            trailer_map[commit] = TrailerPair(github_pull=pr_id, rebased_from=source_merge)
            match_kinds["merge-pr"] += 1
            continue

        target_patch_id = patch_id(target_repo, commit, path_maps, is_source=False)
        candidates = list(source_by_patch.get(target_patch_id, [])) if target_patch_id else []
        kind = "patch-id"
        if candidates:
            same_subject = [candidate for candidate in candidates if source_subjects.get(candidate) == subject]
            if same_subject:
                candidates = same_subject
        elif allow_subject_fallback:
            candidates = list(source_by_subject.get(subject, []))
            kind = "subject-fallback"

        target_pr = target_pr_by_commit.get(commit)
        if target_pr:
            same_pr = [candidate for candidate in candidates if source_pr_by_commit.get(candidate) == target_pr]
            if same_pr:
                candidates = same_pr

        unused = [candidate for candidate in candidates if candidate not in used_source]
        if unused:
            candidates = unused

        if not candidates:
            issues.append((commit, subject, f"no {kind} match", [], target_pr))
            continue
        if len(candidates) > 1 and not allow_ordered_duplicates:
            issues.append((commit, subject, f"ambiguous {kind} match", candidates, target_pr))
            continue

        candidates.sort(key=lambda candidate: source_order.get(candidate, 10**9))
        source_commit = candidates[0]
        used_source.add(source_commit)
        pr_id = source_pr_by_commit.get(source_commit)
        if not pr_id:
            issues.append((commit, subject, f"source commit has no PR context: {source_commit}", candidates, target_pr))
            continue
        trailer_map[commit] = TrailerPair(github_pull=pr_id, rebased_from=source_commit)
        match_kinds[kind + "-ordered" if len(candidates) > 1 else kind] += 1

    return trailer_map, match_kinds, issues


def build_target_descendant_trailer_map(
    target_repo: Path,
    target_ref: str,
    target_import_tip: str,
) -> tuple[dict[str, TrailerPair], Counter[str], list[str]]:
    pr_by_commit, _ = pr_context_from_first_parent(target_repo, target_ref)
    descendants = git(target_repo, "rev-list", "--reverse", "--topo-order", f"{target_import_tip}..{target_ref}").splitlines()
    trailer_map: dict[str, TrailerPair] = {}
    match_kinds: Counter[str] = Counter()
    without_github_pull: list[str] = []

    for commit in descendants:
        pr_id = pr_by_commit.get(commit)
        trailer_map[commit] = TrailerPair(github_pull=pr_id, rebased_from=commit)
        if pr_id:
            match_kinds["target-pr"] += 1
        else:
            match_kinds["target-no-pr"] += 1
            without_github_pull.append(commit)

    return trailer_map, match_kinds, without_github_pull


def apply_trailers(message: str, trailers: TrailerPair) -> str:
    args = ["git", "interpret-trailers", "--if-exists=addIfDifferent"]
    if trailers.github_pull:
        args.extend(["--trailer", f"Github-Pull: {trailers.github_pull}"])
    args.extend(["--trailer", f"Rebased-From: {trailers.rebased_from}"])
    return run(
        args,
        input_data=message,
    ).stdout


def rewrite_history(
    target_repo: Path,
    target_ref: str,
    trailer_map: dict[str, TrailerPair],
) -> tuple[str, dict[str, str], int]:
    commits = git(target_repo, "rev-list", "--reverse", "--topo-order", target_ref).splitlines()
    rewrite: dict[str, str] = {}
    changed_messages = 0

    for index, old_commit in enumerate(commits, 1):
        raw = git(
            target_repo,
            "show",
            "-s",
            "--format=%T%x00%P%x00%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI%x00%B",
            old_commit,
        )
        tree, parent_line, author_name, author_email, author_date, committer_name, committer_email, committer_date, message = raw.split(
            "\x00", 8
        )

        old_parents = parent_line.split()
        new_parents = [rewrite.get(parent, parent) for parent in old_parents]

        trailers = trailer_map.get(old_commit)
        parent_changed = old_parents != new_parents
        if not trailers and not parent_changed:
            rewrite[old_commit] = old_commit
            continue

        parent_args: list[str] = []
        for parent in new_parents:
            parent_args.extend(["-p", parent])

        if trailers:
            message = apply_trailers(message, trailers)
            changed_messages += 1

        env = os.environ.copy()
        env.update(
            {
                "GIT_AUTHOR_NAME": author_name,
                "GIT_AUTHOR_EMAIL": author_email,
                "GIT_AUTHOR_DATE": author_date,
                "GIT_COMMITTER_NAME": committer_name,
                "GIT_COMMITTER_EMAIL": committer_email,
                "GIT_COMMITTER_DATE": committer_date,
            }
        )
        new_commit = git(target_repo, "commit-tree", tree, *parent_args, input_data=message, env=env).strip()
        rewrite[old_commit] = new_commit
        if index % 200 == 0 or index == len(commits):
            print(f"processed {index}/{len(commits)}")

    return rewrite[commits[-1]], rewrite, changed_messages


def write_map_file(
    path: Path,
    *,
    branch: str,
    old_head: str,
    new_head: str | None,
    target_import_tip: str,
    trailer_map: dict[str, TrailerPair],
    rewrite: dict[str, str] | None,
    match_kinds: Counter[str],
    without_github_pull: list[str],
) -> None:
    data = {
        "branch": branch,
        "old_head": old_head,
        "new_head": new_head,
        "target_import_tip": target_import_tip,
        "target_import_tip_new": rewrite.get(target_import_tip) if rewrite else None,
        "match_kinds": dict(match_kinds),
        "trailers": {
            commit: {
                **({"Github-Pull": trailers.github_pull} if trailers.github_pull else {}),
                "Rebased-From": trailers.rebased_from,
            }
            for commit, trailers in sorted(trailer_map.items())
        },
        "without_github_pull": without_github_pull,
        "old_to_new": rewrite or {},
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a new branch with Github-Pull and Rebased-From trailers on filtered gui-qml commits.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--source", default=DEFAULT_SOURCE_REPO, help="source gui-qml repository")
    parser.add_argument("--source-ref", default=DEFAULT_SOURCE_REF, help="source ref used for provenance")
    parser.add_argument("--target", default=".", help="target filtered repository")
    parser.add_argument("--target-ref", default=DEFAULT_TARGET_REF, help="target ref to rewrite")
    parser.add_argument(
        "--target-import-tip",
        default=DEFAULT_TARGET_IMPORT_TIP,
        help="last commit in the target that came from the filtered source; use 'auto' to match the source tip subject",
    )
    parser.add_argument(
        "--tag-target-descendants",
        dest="tag_target_descendants",
        action="store_true",
        default=DEFAULT_TAG_TARGET_DESCENDANTS,
        help="also tag commits after --target-import-tip using target branch PR merge context",
    )
    parser.add_argument(
        "--no-tag-target-descendants",
        dest="tag_target_descendants",
        action="store_false",
        default=argparse.SUPPRESS,
        help="only tag commits through --target-import-tip",
    )
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help="new branch to create at the rewritten tip")
    parser.add_argument("--force-branch", action="store_true", help="overwrite --branch if it already exists")
    parser.add_argument("--switch", action="store_true", help="switch the target checkout to the new branch")
    parser.add_argument(
        "--path-map",
        action="append",
        type=parse_path_map,
        help="source-to-target path map; repeat to map multiple roots",
    )
    parser.add_argument(
        "--allow-subject-fallback",
        action="store_true",
        help="fall back to subject matching when patch-id matching fails",
    )
    parser.add_argument(
        "--strict-duplicates",
        action="store_true",
        help="fail instead of resolving duplicate patch-id matches by source order",
    )
    parser.add_argument("--write-map", type=Path, help="write the old-to-new rewrite/provenance map to this file")
    parser.add_argument("--dry-run", action="store_true", help="build and validate the map without writing commits")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        source_repo = git_top_level(Path(args.source).resolve())
        target_repo = git_top_level(Path(args.target).resolve())
        source_ref = rev_parse(source_repo, args.source_ref)
        target_ref = rev_parse(target_repo, args.target_ref)
        path_maps = args.path_map or [parse_path_map(value) for value in DEFAULT_PATH_MAPS]

        target_import_tip = (
            find_target_import_tip(target_repo, target_ref, source_repo, source_ref)
            if args.target_import_tip == "auto"
            else rev_parse(target_repo, args.target_import_tip)
        )

        trailer_map, match_kinds, issues = build_trailer_map(
            source_repo=source_repo,
            source_ref=source_ref,
            target_repo=target_repo,
            target_import_tip=target_import_tip,
            path_maps=path_maps,
            allow_subject_fallback=args.allow_subject_fallback,
            allow_ordered_duplicates=not args.strict_duplicates,
        )
        without_github_pull: list[str] = []
        if args.tag_target_descendants:
            target_trailers, target_match_kinds, without_github_pull = build_target_descendant_trailer_map(
                target_repo, target_ref, target_import_tip
            )
            duplicate_commits = sorted(set(trailer_map).intersection(target_trailers))
            if duplicate_commits:
                raise ScriptError("internal error: descendant map overlaps filtered import map")
            trailer_map.update(target_trailers)
            match_kinds.update(target_match_kinds)

        print(f"source: {source_repo} {source_ref}")
        print(f"target: {target_repo} {target_ref}")
        print(f"target import tip: {target_import_tip}")
        print(f"matched commits: {len(trailer_map)}")
        print("match kinds: " + ", ".join(f"{key}={value}" for key, value in sorted(match_kinds.items())))
        if without_github_pull:
            print("commits without Github-Pull:")
            for commit in without_github_pull:
                print(f"  {commit} {commit_subject(target_repo, commit)}")

        if issues:
            print("\nUnresolved commits:", file=sys.stderr)
            for commit, subject, reason, candidates, pr_id in issues[:80]:
                suffix = f" pr={pr_id}" if pr_id else ""
                candidate_text = " candidates=" + ",".join(candidates[:8]) if candidates else ""
                print(f"  {commit} {subject!r}: {reason}{suffix}{candidate_text}", file=sys.stderr)
            raise ScriptError(f"could not map {len(issues)} target commit(s)")

        if args.dry_run:
            if args.write_map:
                write_map_file(
                    args.write_map,
                    branch=args.branch,
                    old_head=target_ref,
                    new_head=None,
                    target_import_tip=target_import_tip,
                    trailer_map=trailer_map,
                    rewrite=None,
                    match_kinds=match_kinds,
                    without_github_pull=without_github_pull,
                )
            return 0

        if args.switch:
            ensure_clean(target_repo, "target checkout")
        if branch_exists(target_repo, args.branch) and not args.force_branch:
            raise ScriptError(f"branch already exists: {args.branch}; pass --force-branch to overwrite it")

        new_head, rewrite, changed_messages = rewrite_history(target_repo, target_ref, trailer_map)
        branch_args = ["branch"]
        if args.force_branch:
            branch_args.append("-f")
        branch_args.extend([args.branch, new_head])
        git(target_repo, *branch_args)
        if args.switch:
            git(target_repo, "switch", args.branch)

        old_tree = git(target_repo, "rev-parse", f"{target_ref}^{{tree}}").strip()
        new_tree = git(target_repo, "rev-parse", f"{new_head}^{{tree}}").strip()
        if old_tree != new_tree:
            raise ScriptError(f"rewritten branch tree differs from target ref: {old_tree} != {new_tree}")

        if args.write_map:
            write_map_file(
                args.write_map,
                branch=args.branch,
                old_head=target_ref,
                new_head=new_head,
                target_import_tip=target_import_tip,
                trailer_map=trailer_map,
                rewrite=rewrite,
                match_kinds=match_kinds,
                without_github_pull=without_github_pull,
            )

        print(f"created branch: {args.branch}")
        print(f"old head: {target_ref}")
        print(f"new head: {new_head}")
        print(f"changed messages: {changed_messages}")
        print(f"tree: {new_tree}")
        return 0
    except ScriptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
