"""HW7 Part 6 - file tools and a bash safety gate (pure Python, no model needed).

All file tools are confined to a sandbox root (a temporary course directory);
paths that resolve outside it are rejected. Every tool returns
{"success": bool, "data"?: ..., "error"?: str}.
"""

from __future__ import annotations

import difflib
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Safety gate
# --------------------------------------------------------------------------- #
SAFE_PREFIXES: tuple[str, ...] = (
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "find",
    "echo",
    "python3",
    "git status",
    "git diff",
    "git log",
)

# Independent deny-list. Checked BEFORE and regardless of SAFE_PREFIXES.
# v1 only matched the literal "rm -rf"; the 10-command test showed that
# `find . -name '*.pyc' -delete` was a FALSE ALLOW (find is a safe prefix), so
# recursive deletion now covers every rm flag order, find -delete/-exec rm and
# Python rmtree one-liners.
DESTRUCTIVE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "recursive deletion",
        re.compile(
            r"\brm\s+(-[a-zA-Z]*[rR][a-zA-Z]*\b|.*\s-[a-zA-Z]*[rR]\b|.*--recursive)"
            r"|\bfind\b.*\s-delete\b"
            r"|\bfind\b.*-exec(dir)?\s+rm\b"
            r"|\bxargs\s+rm\b"
            r"|shutil\.rmtree|\brmdir\b"
        ),
    ),
    ("privilege escalation", re.compile(r"\b(sudo|doas|su)\b|\bpkexec\b")),
    (
        "permission/ownership change",
        re.compile(r"\b(chmod|chown|chgrp|chattr|setfacl)\b|os\.chmod|os\.chown"),
    ),
    (
        "raw-device write",
        re.compile(r"\bof=/dev/|>\s*/dev/(sd|disk|nvme|hd|rdisk)|\bshred\b"),
    ),
    (
        "filesystem creation",
        re.compile(r"\b(mkfs(\.\w+)?|mke2fs|newfs|mkswap)\b|diskutil\s+erase"),
    ),
    (
        "redirection to root path",
        re.compile(r">>?\s*/(?!dev/null\b)|\btee\s+(-a\s+)?/"),
    ),
]


def is_destructive(command: str) -> bool:
    """True if the command matches any destructive pattern."""
    return bool(destructive_reasons(command))


def destructive_reasons(command: str) -> list[str]:
    text = " ".join(str(command).split())
    return [label for label, pattern in DESTRUCTIVE_PATTERNS if pattern.search(text)]


def _matches_safe_prefix(command: str) -> bool:
    text = " ".join(command.split())
    return any(text == p or text.startswith(p + " ") for p in SAFE_PREFIXES)


def confirm_bash(command: str, auto_approve: bool = False) -> dict[str, Any]:
    """Return {"allow": bool, "reason": str}.

    Order matters: the destructive deny-list is evaluated first, so a command
    that starts with a SAFE_PREFIX (e.g. `echo x > /etc/hosts`) is still blocked
    unless the caller explicitly confirms with auto_approve=True.
    """
    reasons = destructive_reasons(command)
    if reasons:
        if auto_approve:
            return {
                "allow": True,
                "reason": f"destructive ({', '.join(reasons)}) "
                "but explicitly confirmed",
            }
        return {
            "allow": False,
            "reason": f"blocked: destructive ({', '.join(reasons)}); "
            "explicit confirmation required",
        }
    if _matches_safe_prefix(command):
        return {"allow": True, "reason": "allowed: matches SAFE_PREFIXES"}
    if auto_approve:
        return {
            "allow": True,
            "reason": "allowed: not in SAFE_PREFIXES, explicitly confirmed",
        }
    return {
        "allow": False,
        "reason": "blocked: not in SAFE_PREFIXES; confirmation required",
    }


# --------------------------------------------------------------------------- #
# File tools
# --------------------------------------------------------------------------- #
class FileTools:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, path: str) -> Path:
        candidate = (self.root / path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise PermissionError(f"path escapes sandbox: {path}")
        return candidate

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def read_file(self, path: str, max_lines: int | None = None) -> dict[str, Any]:
        try:
            target = self._path(path)
            lines = target.read_text(encoding="utf-8").splitlines()
        except (OSError, PermissionError, UnicodeDecodeError) as exc:
            return {"success": False, "error": str(exc)}
        shown = lines if max_lines is None else lines[: max(0, int(max_lines))]
        return {
            "success": True,
            "data": {
                "path": self._rel(target),
                "content": "\n".join(shown),
                "lines_returned": len(shown),
                "total_lines": len(lines),
                "truncated": len(shown) < len(lines),
            },
        }

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        try:
            target = self._path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except (OSError, PermissionError) as exc:
            return {"success": False, "error": str(exc)}
        return {
            "success": True,
            "data": {"path": self._rel(target), "bytes": len(content.encode())},
        }

    def edit_file(self, path: str, old: str, new: str) -> dict[str, Any]:
        """Replace exactly one occurrence of `old`; return a short unified diff."""
        try:
            target = self._path(path)
            before = target.read_text(encoding="utf-8")
        except (OSError, PermissionError) as exc:
            return {"success": False, "error": str(exc)}
        count = before.count(old)
        if count != 1:
            return {
                "success": False,
                "error": f"old text must occur exactly once (found {count})",
            }
        after = before.replace(old, new, 1)
        target.write_text(after, encoding="utf-8")
        diff = list(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=f"a/{self._rel(target)}",
                tofile=f"b/{self._rel(target)}",
                n=1,
                lineterm="",
            )
        )
        return {
            "success": True,
            "data": {"path": self._rel(target), "diff": "\n".join(diff[:30])},
        }

    def glob_files(self, pattern: str) -> dict[str, Any]:
        if ".." in Path(pattern).parts:
            return {"success": False, "error": "pattern may not contain '..'"}
        matches = sorted(self._rel(p) for p in self.root.glob(pattern) if p.is_file())
        return {"success": True, "data": {"pattern": pattern, "files": matches}}

    def search_in_files(
        self, query: str, file_pattern: str = "**/*", max_results: int = 50
    ) -> dict[str, Any]:
        files = self.glob_files(file_pattern)
        if not files["success"]:
            return files
        hits = []
        for rel in files["data"]["files"]:
            try:
                text = (self.root / rel).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    hits.append({"path": rel, "line": number, "text": line.strip()})
                    if len(hits) >= max_results:
                        break
        return {
            "success": True,
            "data": {"query": query, "file_pattern": file_pattern, "matches": hits},
        }

    def bash(
        self, command: str, auto_approve: bool = False, timeout: int = 10
    ) -> dict[str, Any]:
        gate = confirm_bash(command, auto_approve)
        if not gate["allow"]:
            return {"success": False, "error": gate["reason"], "data": {"gate": gate}}
        try:
            completed = subprocess.run(
                shlex.split(command) if not re.search(r"[|><;&]", command) else command,
                shell=bool(re.search(r"[|><;&]", command)),
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            return {"success": False, "error": str(exc), "data": {"gate": gate}}
        return {
            "success": completed.returncode == 0,
            "data": {
                "gate": gate,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-2000:],
                "stderr": completed.stderr[-1000:],
            },
        }
