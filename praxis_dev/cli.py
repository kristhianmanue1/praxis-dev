"""Command-line entry point for the read-only Praxis CLI (F1, proposed).

Grammar (per ``docs/contrato-cli.md``)::

    praxis project status [repo] [--format json]
    praxis project audit  [repo] [--profile <id>] [--format json]
    praxis adr list  [repo] [--status <estado>] [--format json]
    praxis adr show  [repo] <adr-id> [--format json]
    praxis adr audit [repo] [--format json]

Output contract
---------------
* Human output goes to stdout; diagnostics go to stderr.
* ``--format json`` emits EXCLUSIVELY the contractual JSON object on stdout
  (nothing else). The ``audit`` object satisfies
  ``schemas/audit-result.schema.json``; the ``status`` object is the stable
  ``praxis/project-status/v1`` payload documented below; ``adr list`` and
  ``adr show`` emit the stable ``praxis/adr-list/v1`` and
  ``praxis/adr-summary/v1`` payloads (informational, intentionally not in
  ``schemas/``).
* Values are not silently coerced; unknown options/profiles are usage errors.

Exit codes (``docs/contrato-cli.md`` §3)::

    0  operation completed / conformance (audit result == pass)
    1  precondition or conformance failure (audit result == fail)
    2  invalid usage or malformed contract (bad flags, unknown command,
       unparseable ``.praxis.toml``, repo not found)
    3  inconclusive by environment/capability (e.g. unreadable config)

No command in this module writes to the target repository.

Status payload ``praxis/project-status/v1``
--------------------------------------------
A new informational surface (NOT added to ``schemas/``, so the versioned
standard is unchanged). Stable fields:

    schema             "praxis/project-status/v1"
    tool_version       CLI version string
    repo               absolute path of the audited repository
    config_present     bool   -- whether .praxis.toml exists
    config_parseable   bool   -- whether .praxis.toml parsed as TOML
    config_error       string | null  -- parse/read error, if any
    project_id         string | null  -- from .praxis.toml, else null
    standard_version   string         -- from .praxis.toml, else "unknown"
    profile            string         -- from .praxis.toml, else "unknown"
    lifecycle          string         -- from .praxis.toml, else "unknown"
    observed_revision  string | null  -- git HEAD sha, else null
    observed_at        string         -- UTC RFC 3339 with trailing "Z"

New compatible fields may be added later; removing or reinterpreting a field
requires a new payload version.
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Any, Iterator

from praxis_dev import adr as adr_mod
from praxis_dev import project as project_mod
from praxis_dev.adr import (
    ADR_ID_PATTERN,
    ADR_STATUSES,
    audit_adrs,
    list_adrs,
    show_adr,
)
from praxis_dev.project import (
    EXIT_FAIL,
    EXIT_INCONCLUSIVE,
    EXIT_PASS,
    ConfigMalformed,
    ConfigUnreadable,
    KNOWN_PROFILES,
    audit_project,
    status_payload,
)

# EXIT_PASS/EXIT_FAIL/EXIT_INCONCLUSIVE come from praxis_dev.project (single
# home). EXIT_USAGE is CLI-specific (project.audit_project never returns it).
EXIT_USAGE = 2


class _Usage(Exception):
    """Internal signal for a usage/contract error (exit code 2)."""


# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #
def _emit_json(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, indent=2, sort_keys=True))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _emit_audit_human(result: dict[str, Any], *, domain: str = "project") -> None:
    sys.stdout.write(
        "praxis {domain} audit: {result} (profile={profile}, level={level}, "
        "findings={nfindings}, diagnostics={ndiagnostics})\n".format(
            domain=domain,
            result=result["result"],
            profile=result["profile"],
            level=result["level"],
            nfindings=len(result["findings"]),
            ndiagnostics=len(result["diagnostics"]),
        )
    )
    sys.stdout.flush()
    for finding in result["findings"]:
        sys.stderr.write(
            f"> [{finding['severity']}] {finding['id']}: {finding['message']}\n"
        )
    for diag in result["diagnostics"]:
        sys.stderr.write(f"# [{diag['level']}] {diag['code']}: {diag['message']}\n")
    sys.stderr.flush()


def _emit_status_human(payload: dict[str, Any]) -> None:
    lines = [
        f"praxis project status: {payload['repo']}",
        f"  config: present={payload['config_present']} parseable={payload['config_parseable']}",
        f"  project_id: {payload['project_id']}",
        f"  standard_version: {payload['standard_version']}",
        f"  profile: {payload['profile']}",
        f"  lifecycle: {payload['lifecycle']}",
        f"  head: {payload['observed_revision']}",
        f"  observed_at: {payload['observed_at']}",
    ]
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def _fail_usage(message: str) -> int:
    sys.stderr.write(f"praxis: error: {message}\n")
    sys.stderr.flush()
    return EXIT_USAGE


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def _parse(args: list[str], *, allow_profile: bool) -> tuple[Path, str | None, str]:
    """Parse the common ``[repo] [--profile id] [--format json]`` tail.

    Raises :class:`_Usage` on any contract problem. Returns
    ``(repo, profile, format)`` where ``format`` is ``"json"`` or ``"human"``.
    """
    positionals: list[str] = []
    profile: str | None = None
    fmt = "human"
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--format":
            index += 1
            if index >= len(args):
                raise _Usage("missing value for --format")
            if args[index] != "json":
                raise _Usage("--format only supports 'json'")
            fmt = "json"
        elif token == "--profile":
            if not allow_profile:
                raise _Usage("--profile is not valid for this command")
            index += 1
            if index >= len(args):
                raise _Usage("missing value for --profile")
            profile = args[index]
            if profile not in KNOWN_PROFILES:
                raise _Usage(f"unknown profile {profile!r}")
        elif token.startswith("-") and token != "-":
            raise _Usage(f"unknown option {token!r}")
        else:
            positionals.append(token)
        index += 1
    if len(positionals) > 1:
        raise _Usage("expected at most one repo argument")
    repo = Path(positionals[0]) if positionals else Path.cwd()
    return repo, profile, fmt


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def _cmd_status(args: list[str]) -> int:
    try:
        repo, _profile, fmt = _parse(args, allow_profile=False)
    except _Usage as exc:
        return _fail_usage(str(exc))
    if not repo.is_dir():
        return _fail_usage(f"repo not found: {repo}")
    payload = status_payload(repo)
    if fmt == "json":
        _emit_json(payload)
    else:
        _emit_status_human(payload)
    return EXIT_PASS


def _cmd_audit(args: list[str]) -> int:
    try:
        repo, profile, fmt = _parse(args, allow_profile=True)
    except _Usage as exc:
        return _fail_usage(str(exc))
    if not repo.is_dir():
        return _fail_usage(f"repo not found: {repo}")
    try:
        result, exit_code = audit_project(repo, profile)
    except ConfigMalformed as exc:
        # Contract malformed: no audit-result object is emitted.
        return _fail_usage(f"malformed .praxis.toml: {exc}")
    except ConfigUnreadable as exc:
        sys.stderr.write(f"praxis: inconclusive: unreadable .praxis.toml: {exc}\n")
        sys.stderr.flush()
        return EXIT_INCONCLUSIVE
    if fmt == "json":
        _emit_json(result)
    else:
        _emit_audit_human(result)
    return exit_code


def _cmd_project(args: list[str]) -> int:
    if not args:
        return _fail_usage("project requires an operation")
    operation, rest = args[0], args[1:]
    if operation == "status":
        return _cmd_status(rest)
    if operation == "audit":
        return _cmd_audit(rest)
    return _fail_usage(f"unknown project operation {operation!r}")


# --------------------------------------------------------------------------- #
# adr domain
# --------------------------------------------------------------------------- #
def _parse_adr(
    args: list[str], *, allow_status: bool
) -> tuple[list[str], str | None, str]:
    """Parse the ADR option tail.

    Returns ``(positionals, status, format)`` where ``format`` is ``"json"`` or
    ``"human"``. Each command interprets ``positionals`` (repo and, for show,
    the ADR id). Raises :class:`_Usage` on any contract problem.
    """
    positionals: list[str] = []
    status: str | None = None
    fmt = "human"
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--format":
            index += 1
            if index >= len(args):
                raise _Usage("missing value for --format")
            if args[index] != "json":
                raise _Usage("--format only supports 'json'")
            fmt = "json"
        elif token == "--status":
            if not allow_status:
                raise _Usage("--status is not valid for this command")
            index += 1
            if index >= len(args):
                raise _Usage("missing value for --status")
            status = args[index]
            if status not in ADR_STATUSES:
                raise _Usage(f"unknown status {status!r}")
        elif token.startswith("-") and token != "-":
            raise _Usage(f"unknown option {token!r}")
        else:
            positionals.append(token)
        index += 1
    return positionals, status, fmt


def _emit_list_human(payload: dict[str, Any]) -> None:
    sys.stdout.write(
        f"praxis adr list: {payload['repo']}\n"
        f"  decisions_dir: {payload['decisions_dir']}\n"
        f"  ADRs ({payload['count']}):\n"
    )
    for entry in payload["adrs"]:
        sys.stdout.write(
            f"    [{entry['status']}] {entry['id']} - {entry['title']} ({entry['filename']})\n"
        )
    if payload["unparseable_count"]:
        sys.stdout.write(f"  unparseable ({payload['unparseable_count']}):\n")
        for entry in payload["unparseable"]:
            sys.stderr.write(f"    {entry['filename']}: {entry['problem']}\n")
    sys.stdout.flush()
    sys.stderr.flush()


def _emit_summary_human(payload: dict[str, Any]) -> None:
    if not payload["found"]:
        sys.stdout.write(f"praxis adr show: {payload['id']} not found\n")
        sys.stdout.flush()
        return
    metadata = payload["metadata"]
    sys.stdout.write(
        f"praxis adr show: {payload['id']}\n"
        f"  title: {metadata.get('title')}\n"
        f"  status: {metadata.get('status')}\n"
        f"  file: {payload['path']}\n"
    )
    sys.stdout.flush()


def _cmd_adr_list(args: list[str]) -> int:
    try:
        positionals, status, fmt = _parse_adr(args, allow_status=True)
    except _Usage as exc:
        return _fail_usage(str(exc))
    if len(positionals) > 1:
        return _fail_usage("expected at most one repo argument")
    repo = Path(positionals[0]) if positionals else Path.cwd()
    if not repo.is_dir():
        return _fail_usage(f"repo not found: {repo}")
    payload = list_adrs(repo, status)
    if fmt == "json":
        _emit_json(payload)
    else:
        _emit_list_human(payload)
    return EXIT_PASS


def _cmd_adr_show(args: list[str]) -> int:
    try:
        positionals, _status, fmt = _parse_adr(args, allow_status=False)
    except _Usage as exc:
        return _fail_usage(str(exc))
    if not positionals:
        return _fail_usage("adr show requires an ADR id")
    if len(positionals) > 2:
        return _fail_usage("expected at most one repo and one ADR id")
    if len(positionals) == 2:
        repo, adr_id = Path(positionals[0]), positionals[1]
    else:
        repo, adr_id = Path.cwd(), positionals[0]
    if not repo.is_dir():
        return _fail_usage(f"repo not found: {repo}")
    if ADR_ID_PATTERN.match(adr_id) is None:
        return _fail_usage(f"invalid ADR id {adr_id!r} (expected ADR-NNNN)")
    payload = show_adr(repo, adr_id)
    if fmt == "json":
        _emit_json(payload)
    else:
        _emit_summary_human(payload)
    return EXIT_PASS if payload["found"] else EXIT_FAIL


def _cmd_adr_audit(args: list[str]) -> int:
    try:
        positionals, _status, fmt = _parse_adr(args, allow_status=False)
    except _Usage as exc:
        return _fail_usage(str(exc))
    if len(positionals) > 1:
        return _fail_usage("expected at most one repo argument")
    repo = Path(positionals[0]) if positionals else Path.cwd()
    if not repo.is_dir():
        return _fail_usage(f"repo not found: {repo}")
    result, exit_code = audit_adrs(repo)
    if fmt == "json":
        _emit_json(result)
    else:
        _emit_audit_human(result, domain="adr")
    return exit_code


def _cmd_adr(args: list[str]) -> int:
    if not args:
        return _fail_usage("adr requires an operation")
    operation, rest = args[0], args[1:]
    if operation == "list":
        return _cmd_adr_list(rest)
    if operation == "show":
        return _cmd_adr_show(rest)
    if operation == "audit":
        return _cmd_adr_audit(rest)
    return _fail_usage(f"unknown adr operation {operation!r}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code."""
    args = list(sys.argv[1:]) if argv is None else list(argv)
    if not args:
        return _fail_usage("no command given (try: praxis project status)")
    domain, rest = args[0], args[1:]
    if domain == "project":
        return _cmd_project(rest)
    if domain == "adr":
        return _cmd_adr(rest)
    return _fail_usage(f"unknown domain {domain!r}")


@contextmanager
def _capture_streams() -> Iterator[tuple[StringIO, StringIO]]:
    out, err = StringIO(), StringIO()
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        yield out, err
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err


def run(args: list[str]) -> tuple[int, str, str]:
    """Convenience for tests: run :func:`main` capturing stdout/stderr."""
    with _capture_streams() as (out, err):
        code = main(args)
    return code, out.getvalue(), err.getvalue()


__all__ = [
    "EXIT_FAIL",
    "EXIT_INCONCLUSIVE",
    "EXIT_PASS",
    "EXIT_USAGE",
    "main",
    "run",
]
