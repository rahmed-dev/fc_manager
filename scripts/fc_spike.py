"""FC API spike for task 2.1 of the read-only-core change.

Run it yourself with your own key. It only calls read-only FC methods (the same allowlist as
`fcm`), and it never prints the key or the secret.

    export FCM_API_KEY=...  FCM_API_SECRET=...
    uv run python scripts/fc_spike.py            # writes anonymized fixtures to a temp dir
    uv run python scripts/fc_spike.py --write    # writes them to tests/fixtures/fc/

It answers three questions:
  1. Does the X-Press-Team header select the team for press.api.site.all / bench.all?
  2. What do real FC responses and error bodies look like?
  3. What do the deploy read methods return (deploy_information, deploy_status, and the
     Deploy Candidate Build doc through client.get)?
     The spike never calls a deploy (write) method.
  4. What do the site job reads return (site.running_jobs for one site, and site.job for
     a running job)?
     The spike never calls a migrate (write) method.

Review every fixture before you commit it. The anonymizer replaces names, titles, emails,
IP addresses and host names, but you are the last check.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx

from fc_manager.api.client import DEFAULT_BASE_URL, check_read_method, validate_base_url
from fc_manager.errors import MethodNotAllowed
from fc_manager.redact import Credentials, redact

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "fc"
MAX_TEAMS = 3
MAX_ROWS = 3

SENSITIVE_KEYS = {
    "name", "title", "team", "team_title", "user", "email", "full_name", "first_name",
    "last_name", "host_name", "bench", "group", "server", "proxy_server", "ip", "domain",
    "repository", "repository_url", "repository_owner", "commit_message", "owner",
    "modified_by", "parent_team", "partner_email", "app_title", "deploy_candidate", "site",
    "id",
}  # fmt: skip
PUBLIC_OWNERS = {"frappe"}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SECRET_FIELD_RE = re.compile(r"key|secret|token|password", re.IGNORECASE)
HOST_RE = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}\b")
SAFE_HOSTS = ("example.com", "github.com", "frappe.io", "frappecloud.com", "frappe.cloud")
SAFE_PREFIXES = ("frappe.", "press.", "erpnext.", "hrms.")


def _scrub_host(match: re.Match[str]) -> str:
    host = match.group(0)
    if host.endswith(SAFE_HOSTS) or host.startswith(SAFE_PREFIXES):
        return host
    return "host.example.com"


class Spike:
    def __init__(self, creds: Credentials, base_url: str) -> None:
        self.creds = creds
        self.http = httpx.Client(base_url=base_url, timeout=httpx.Timeout(30.0, connect=10.0))

    def get(
        self, method: str, team: str | None = None, secret: str | None = None, **params: Any
    ) -> httpx.Response:
        try:
            check_read_method(method, params)
        except MethodNotAllowed as exc:
            raise SystemExit(f"refusing: {exc}") from exc
        auth = (
            self.creds.authorization() if secret is None else f"Token {self.creds.api_key}:{secret}"
        )
        headers = {"Authorization": auth, "Accept": "application/json"}
        if team:
            headers["X-Press-Team"] = team
        query = {k: json.dumps(v) if isinstance(v, dict | list) else v for k, v in params.items()}
        return self.http.get(f"/api/method/{method}", params=query, headers=headers)


class Anonymizer:
    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}

    def _placeholder(self, key: str, value: str) -> str:
        if value not in self.mapping:
            n = sum(1 for v in self.mapping.values() if v.startswith(f"{key}-")) + 1
            if "@" in value:
                self.mapping[value] = f"{key}-{n}@example.com"
            elif "." in value and " " not in value:
                self.mapping[value] = f"{key}-{n}.example.com"
            else:
                self.mapping[value] = f"{key}-{n}"
        return self.mapping[value]

    def collect(self, node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            public = str(node.get("repository_owner", "")) in PUBLIC_OWNERS
            # In a running_jobs row (job_detail), `id` is the job and `name` the public job
            # type, such as "Migrate Site". Keep the job type readable.
            job_detail = "id" in node and "steps" in node
            for k, v in node.items():
                if job_detail and k == "name":
                    continue
                if isinstance(v, str) and k in SENSITIVE_KEYS and v and not public:
                    self._placeholder(k, v)
                else:
                    self.collect(v, k)
        elif isinstance(node, list):
            for item in node:
                self.collect(item, key)

    def scrub(self, node: Any) -> Any:
        if isinstance(node, dict):
            return {
                k: "***" if SECRET_FIELD_RE.search(k) and v else self.scrub(v)
                for k, v in node.items()
            }
        if isinstance(node, list):
            return [self.scrub(v) for v in node]
        if isinstance(node, str):
            text = node
            for original in sorted(self.mapping, key=len, reverse=True):
                text = text.replace(original, self.mapping[original])
            text = EMAIL_RE.sub("user@example.com", text)
            text = IPV4_RE.sub("203.0.113.10", text)
            return HOST_RE.sub(_scrub_host, text)
        return node


def body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"_non_json_body": response.text[:500], "_status": response.status_code}


def slim_account(data: Any) -> Any:
    """Keep only what fcm reads from account.get (user, teams). The rest of the body holds
    billing and profile data that a fixture does not need."""
    message = data.get("message") if isinstance(data, dict) else None
    if not isinstance(message, dict):
        return data
    user = message.get("user")
    if isinstance(user, dict):
        user = {k: user.get(k) for k in ("name", "email", "full_name") if k in user}
    return {
        "message": {"user": user, "teams": message.get("teams")},
        "_other_fields": sorted(k for k in message if k not in ("user", "teams")),
    }


def teams_in(response: httpx.Response) -> list[str]:
    rows = (body(response) or {}).get("message") or []
    return sorted({str(r.get("team")) for r in rows if isinstance(r, dict)})


MAX_BENCHES_FOR_DEPLOY = 15
OUTPUT_CHARS = 160


def trim_lists(node: Any, limit: int = MAX_ROWS) -> Any:
    """Trim every nested list to `limit` items (releases, build steps, sites)."""
    if isinstance(node, dict):
        return {k: trim_lists(v, limit) for k, v in node.items()}
    if isinstance(node, list):
        return [trim_lists(v, limit) for v in node[:limit]]
    return node


def slim_candidate(data: Any) -> Any:
    """Build step output holds raw build logs (paths, repository URLs). Keep a short head,
    and keep the first 2 steps of each stage so the fixture shows every stage."""
    message = data.get("message") if isinstance(data, dict) else None
    if isinstance(message, dict):
        kept, per_stage = [], {}
        for step in message.get("build_steps") or []:
            if not isinstance(step, dict):
                continue
            stage = step.get("stage")
            per_stage[stage] = per_stage.get(stage, 0) + 1
            if per_stage[stage] > 2:
                continue
            if isinstance(step.get("output"), str):
                step["output"] = step["output"][:OUTPUT_CHARS]
            kept.append(step)
        message["build_steps"] = kept
    return data


def slim_releases(data: Any) -> Any:
    """Release messages are commit messages, which can be private. Keep a short head of
    public releases only."""
    message = data.get("message") if isinstance(data, dict) else None
    for app in (message or {}).get("apps") or [] if isinstance(message, dict) else []:
        for release in app.get("releases") or []:
            text = str(release.get("message") or "")
            public = str(release.get("public")) in ("1", "True", "true")
            release["message"] = text.splitlines()[0][:60] if public and text else "commit message"
    return data


def slim_job(data: Any) -> Any:
    """Job step output holds raw command logs (paths, site names). Keep a short head."""
    message = data.get("message") if isinstance(data, dict) else None
    for step in (message or {}).get("steps") or [] if isinstance(message, dict) else []:
        if isinstance(step, dict) and isinstance(step.get("output"), str):
            step["output"] = step["output"][:OUTPUT_CHARS]
    return data


def slim_jobs(data: Any) -> Any:
    """running_jobs rows hold the steps with their output. Keep a short head of each."""
    for row in (data or {}).get("message") or [] if isinstance(data, dict) else []:
        if isinstance(row, dict):
            slim_job({"message": row})
            if isinstance(row.get("current"), dict) and isinstance(
                row["current"].get("output"), str
            ):
                row["current"]["output"] = row["current"]["output"][:OUTPUT_CHARS]
    return data


def trim(data: Any) -> Any:
    if isinstance(data, dict) and isinstance(data.get("message"), list):
        return {**data, "message": data["message"][:MAX_ROWS]}
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true", help="write into tests/fixtures/fc/")
    args = parser.parse_args()

    key, secret = os.environ.get("FCM_API_KEY"), os.environ.get("FCM_API_SECRET")
    if not key or not secret:
        print("Set FCM_API_KEY and FCM_API_SECRET first.", file=sys.stderr)
        return 2
    creds = Credentials(key, secret)  # registers both values for redaction
    spike = Spike(creds, validate_base_url(os.environ.get("FCM_BASE_URL", DEFAULT_BASE_URL)))
    raw: dict[str, Any] = {}

    account = spike.get("press.api.account.get")
    print(f"account.get -> HTTP {account.status_code}")
    if account.is_redirect:
        location = account.headers.get("location", "?")
        print(f"FC redirects to {location}. Set FCM_BASE_URL to that host.", file=sys.stderr)
        return 3
    if not account.is_success:
        print(redact(account.text[:300]), file=sys.stderr)
        return 3
    raw["account_get.json"] = slim_account(body(account))
    teams = [
        t["name"] if isinstance(t, dict) else t
        for t in (raw["account_get.json"].get("message") or {}).get("teams") or []
    ]
    print(f"teams found: {len(teams)}")

    # Question 1: does X-Press-Team select the team?
    print("\nX-Press-Team check (site.all per team; 'row teams' = team field of each row):")
    verdict_ok = True
    sample_site: tuple[str, str] | None = None
    for team in teams[:MAX_TEAMS]:
        sites = spike.get("press.api.site.all", team=team)
        rows = (body(sites) or {}).get("message") or []
        row_teams = sorted({str(r.get("team")) for r in rows if isinstance(r, dict)})
        match = all(t == team for t in row_teams)
        verdict_ok &= sites.is_success and (not rows or team in row_teams)
        label = "ok" if match else "has other teams (child teams?)"
        print(
            f"  team #{teams.index(team) + 1}: HTTP {sites.status_code}, {len(rows)} sites, {label}"
        )
        if rows and "site_all.json" not in raw:
            raw["site_all.json"] = trim(body(sites))
            sample_site = (team, rows[0]["name"])
        benches = spike.get("press.api.bench.all", team=team)
        if benches.is_success and body(benches).get("message") and "bench_all.json" not in raw:
            raw["bench_all.json"] = trim(body(benches))
    no_header = spike.get("press.api.site.all")
    print(f"  without header: HTTP {no_header.status_code}")
    if verdict_ok:
        print("\nVERDICT: X-Press-Team selects the team. The design holds.")
    else:
        print("\nVERDICT: X-Press-Team did NOT clearly select the team.")
        print("Stop and tell the maintainer (design Risks: the switch_team fallback).")

    # Question 2: real bodies.
    if sample_site:
        team, site = sample_site
        raw["site_get.json"] = body(spike.get("press.api.site.get", team=team, name=site))
        raw["site_installed_apps.json"] = trim(
            body(spike.get("press.api.site.installed_apps", team=team, name=site))
        )
    # Question 4: site job reads (GET only; no migrate is ever started).
    # FC has no job list that works over GET: site.jobs and client.get_list both fail on
    # the filters string (HTTP 500, AttributeError). running_jobs takes a plain site name.
    if sample_site:
        team, site = sample_site
        print("\nSite job reads:")
        running = spike.get("press.api.site.running_jobs", team=team, name=site)
        print(f"  site.running_jobs -> HTTP {running.status_code}")
        rows = (body(running) or {}).get("message") or []
        print(f"  running jobs: {len(rows)}")
        raw["site_running_jobs.json"] = slim_jobs(trim(body(running)))
        if rows and isinstance(rows[0], dict) and rows[0].get("id"):
            job = spike.get("press.api.site.job", team=team, job=rows[0]["id"])
            raw["site_job.json"] = slim_job(trim_lists(body(job), 30))
            print(f"  site.job ({rows[0].get('name')}) -> HTTP {job.status_code}")

    # Question 3: deploy read methods (GET only; no deploy is ever started).
    print("\nDeploy read methods:")
    deploy_seen = 0
    for team in teams[:MAX_TEAMS]:
        rows = (body(spike.get("press.api.bench.all", team=team)) or {}).get("message") or []
        for bench in rows[:MAX_BENCHES_FOR_DEPLOY]:
            info = spike.get("press.api.bench.deploy_information", team=team, name=bench["name"])
            data = body(info)
            message = data.get("message") if isinstance(data, dict) else None
            if not info.is_success or not isinstance(message, dict):
                print(f"  deploy_information -> HTTP {info.status_code}")
                if "error_deploy_information.json" not in raw:
                    raw["error_deploy_information.json"] = data
                continue
            deploy_seen += 1
            has_update = bool(message.get("update_available"))
            if "bench_deploy_information.json" not in raw or (
                has_update and not raw.get("_deploy_has_update")
            ):
                raw["bench_deploy_information.json"] = trim_lists(slim_releases(data), 12)
                raw["_deploy_has_update"] = has_update
                status = spike.get("press.api.bench.deploy_status", team=team, name=bench["name"])
                raw["bench_deploy_status.json"] = body(status)
                print(f"  deploy_status -> HTTP {status.status_code}")
                last = message.get("last_deploy") or {}
                if isinstance(last, dict) and last.get("name"):
                    build = spike.get(
                        "press.api.client.get",
                        team=team,
                        doctype="Deploy Candidate Build",
                        name=last["name"],
                    )
                    build_body = trim_lists(body(build), 200)
                    raw["deploy_candidate_build.json"] = slim_candidate(build_body)
                    print(f"  client.get Deploy Candidate Build -> HTTP {build.status_code}")
            if raw.get("_deploy_has_update"):
                break
        if raw.get("_deploy_has_update"):
            break
    print(f"  benches read: {deploy_seen}, update found: {bool(raw.get('_deploy_has_update'))}")
    raw.pop("_deploy_has_update", None)

    bad = spike.get("press.api.account.get", secret=secret + "-wrong")
    raw["error_auth.json"] = body(bad)
    print(f"\nwrong secret -> HTTP {bad.status_code}")
    denied = spike.get("press.api.site.all", team="fcm-spike-no-such-team")
    raw["unknown_team_site_all.json"] = trim(body(denied))
    print(f"unknown team -> HTTP {denied.status_code}")
    if denied.is_success:
        got, default = teams_in(denied), teams_in(no_header)
        if not got:
            print("  returned no rows")
        elif got == default:
            print("  returned the DEFAULT team's rows (silent fallback)")
        else:
            print("  returned rows from other teams (not the default team)")
    if teams:
        missing = spike.get("press.api.site.get", team=teams[0], name="fcm-spike-missing.invalid")
        raw["error_not_found.json"] = body(missing)
        print(f"unknown site -> HTTP {missing.status_code}")

    anonymizer = Anonymizer()
    for data in raw.values():
        anonymizer.collect(data)
    out_dir = FIXTURE_DIR if args.write else Path(tempfile.mkdtemp(prefix="fc-spike-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in raw.items():
        text = json.dumps(anonymizer.scrub(data), indent=2) + "\n"
        if key in text or secret in text:
            print(f"refusing to write {name}: it still holds a credential", file=sys.stderr)
            return 1
        (out_dir / name).write_text(text)
    print(f"\nwrote {len(raw)} anonymized fixtures to {out_dir}")
    print("Review them by eye before you commit anything.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
