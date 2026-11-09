"""Deploy service: deploy app updates to one FC bench (release group).

This layer has no CLI dependency, so the TUI can reuse it. It never prompts. Every FC
request goes to the team of the bench only (scoped queries). The only write is `start()`.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from fc_manager.api.client import FCClient
from fc_manager.errors import DeployFailed, SiteUpdateUnknown, UsageError
from fc_manager.inventory import Bench
from fc_manager.redact import redact

DEPLOY_METHOD = "press.api.bench.deploy_and_update"
BUILD_DOCTYPE = "Deploy Candidate Build"
POLL_SECONDS = 2.0
# Polls with no pipeline and no new build before the watch gives up (about 30 s).
IDLE_POLLS_LIMIT = 15
# FC moves each selected site in its own job (backup, move, migrate) after the new bench is
# active. A big site takes time; after this limit the result is reported as not known.
SITE_UPDATE_LIMIT_SECONDS = 30 * 60
BUILD_DONE = {"Success", "Failure"}
MESSAGE_CHARS = 500


def _str(value: Any) -> str:
    return "" if value is None else str(value)


def _short(text: str) -> str:
    return text[:7] if len(text) > 7 else text


def _flag(value: Any) -> bool:
    return str(value).lower() in ("1", "true")


# --- data -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Release:
    name: str
    hash: str
    tag: str
    message: str  # first line only; the full text can be a private commit message
    yanked: bool

    @property
    def version(self) -> str:
        return self.tag or _message_version(self.message) or _short(self.hash) or self.name


@dataclass(frozen=True)
class AppUpdate:
    app: str
    title: str
    source: str
    branch: str
    current_branch: str
    current_hash: str
    current_tag: str
    will_branch_change: bool
    next: Release | None  # the release FC offers; None when there is no usable update

    @property
    def current_version(self) -> str:
        return self.current_tag or _short(self.current_hash) or "not installed"

    @property
    def next_version(self) -> str:
        return self.next.version if self.next else self.current_version

    @property
    def has_update(self) -> bool:
        return self.next is not None


@dataclass(frozen=True)
class DeploySite:
    name: str
    server: str
    bench: str  # the FC bench (not release group) the site runs on now
    row: dict  # the row as FC sent it; the deploy request sends it back


@dataclass(frozen=True)
class DeployInfo:
    bench: Bench
    apps: list[AppUpdate]
    removed_apps: list[str]
    sites: list[DeploySite]
    update_available: bool
    deploy_in_progress: bool
    pipeline_running: bool
    bench_creation_underway: bool
    last_build: str

    @property
    def updates(self) -> list[AppUpdate]:
        return [app for app in self.apps if app.has_update]

    @property
    def busy(self) -> bool:
        return self.deploy_in_progress or self.pipeline_running or self.bench_creation_underway

    @property
    def nothing_to_deploy(self) -> bool:
        return not self.updates and not self.removed_apps


@dataclass(frozen=True)
class DeployPlan:
    bench: Bench
    apps: list[AppUpdate]
    sites: list[DeploySite]
    removed_apps: list[str]
    last_build: str  # the build before this deploy; the watch looks for a newer one

    @property
    def bench_only(self) -> bool:
        return not self.sites

    def payload(self) -> dict[str, Any]:
        """The exact body of the deploy request, built from FC data only."""
        apps = []
        for app in self.apps:
            assert app.next is not None  # plan() keeps apps with a usable release only
            apps.append(
                {
                    "app": app.app,
                    "source": app.source,
                    "release": app.next.name,
                    "hash": app.next.hash,
                }
            )
        sites = [
            {**site.row, "skip_failing_patches": False, "skip_backups": False}
            for site in self.sites
        ]
        return {"name": self.bench.name, "apps": apps, "sites": sites, "run_will_fail_check": True}


@dataclass(frozen=True)
class BuildStep:
    stage: str
    step: str
    status: str
    duration: str
    cached: bool

    @property
    def label(self) -> str:
        return f"{self.stage}: {self.step}" if self.step else self.stage


@dataclass(frozen=True)
class DeployState:
    """One look at a deploy. `stage` is one of: idle, starting, validating, building,
    finishing, updating_sites, success, failure. `starting` means FC shows no check and no
    build yet. `sites` holds (site, moved) during updating_sites and after success."""

    stage: str
    build: str = ""
    status: str = ""
    steps: tuple[BuildStep, ...] = ()
    message: str = ""
    sites: tuple[tuple[str, bool], ...] = field(default=())  # (site, moved) after success
    # Liveness of the watch, not of the deploy: when FC last answered a poll, and how many
    # polls ran. Not part of equality, so two looks with the same FC data compare equal.
    checked_at: float = field(default=0.0, compare=False)
    polls: int = field(default=0, compare=False)

    @property
    def final(self) -> bool:
        return self.stage in ("success", "failure")

    @property
    def failed_step(self) -> BuildStep | None:
        return next((s for s in self.steps if s.status == "Failure"), None)

    @property
    def current_step(self) -> BuildStep | None:
        running = next((s for s in self.steps if s.status == "Running"), None)
        return running or next((s for s in self.steps if s.status == "Pending"), None)


# --- parsers --------------------------------------------------------------------------


# FC release commits often have no tag, only a message like "Bumped to Version 16.55.2".
_VERSION_IN_MESSAGE = re.compile(r"\bversion\s+v?(\d+(?:\.\d+){1,3})\b", re.IGNORECASE)


def _message_version(message: str) -> str:
    match = _VERSION_IN_MESSAGE.search(message)
    return f"v{match.group(1)}" if match else ""


def parse_release(row: dict) -> Release:
    text = _str(row.get("message")).strip()
    return Release(
        name=_str(row.get("name")),
        hash=_str(row.get("hash")),
        tag=_str(row.get("tag")),
        message=text.splitlines()[0][:100] if text else "",
        yanked=_flag(row.get("is_yanked")),
    )


def parse_app_update(row: dict) -> AppUpdate:
    next_name = _str(row.get("next_release"))
    releases = [parse_release(r) for r in row.get("releases") or [] if isinstance(r, dict)]
    usable = next((r for r in releases if r.name == next_name and not r.yanked and r.hash), None)
    has_update = bool(row.get("update_available")) and usable is not None
    return AppUpdate(
        app=_str(row.get("app") or row.get("name")),
        title=_str(row.get("title")),
        source=_str(row.get("source")),
        branch=_str(row.get("branch")),
        current_branch=_str(row.get("current_branch")),
        current_hash=_str(row.get("current_hash")),
        current_tag=_str(row.get("current_tag")),
        will_branch_change=bool(row.get("will_branch_change")),
        next=usable if has_update else None,
    )


def parse_removed_app(row: Any) -> str:
    if isinstance(row, dict):
        return _str(row.get("app") or row.get("name") or row.get("title"))
    return _str(row)


def parse_deploy_info(data: Any, bench: Bench) -> DeployInfo:
    data = data if isinstance(data, dict) else {}
    last = data.get("last_deploy")
    return DeployInfo(
        bench=bench,
        apps=[parse_app_update(r) for r in data.get("apps") or [] if isinstance(r, dict)],
        removed_apps=[a for a in map(parse_removed_app, data.get("removed_apps") or []) if a],
        sites=[
            DeploySite(
                name=_str(r.get("name")),
                server=_str(r.get("server")),
                bench=_str(r.get("bench")),
                row=r,
            )
            for r in data.get("sites") or []
            if isinstance(r, dict) and r.get("name")
        ],
        update_available=bool(data.get("update_available")),
        deploy_in_progress=bool(data.get("deploy_in_progress")),
        pipeline_running=bool(data.get("has_running_release_pipeline")),
        bench_creation_underway=bool(data.get("bench_creation_underway")),
        last_build=_str(last.get("name")) if isinstance(last, dict) else "",
    )


def parse_build(data: Any) -> DeployState:
    data = data if isinstance(data, dict) else {}
    status = _str(data.get("status"))
    steps = tuple(
        BuildStep(
            stage=_str(s.get("stage")),
            step=_str(s.get("step")),
            status=_str(s.get("status")),
            duration=_str(s.get("duration")),
            cached=_flag(s.get("cached")),
        )
        for s in data.get("build_steps") or []
        if isinstance(s, dict)
    )
    stage = {"Success": "finishing", "Failure": "failure"}.get(status, "building")
    message = redact(_str(data.get("build_error")).strip())[:MESSAGE_CHARS]
    return DeployState(
        stage=stage, build=_str(data.get("name")), status=status, steps=steps, message=message
    )


# --- service --------------------------------------------------------------------------


class DeployService:
    def __init__(self, client: FCClient) -> None:
        self.client = client

    def _call(self, bench: Bench, method: str, **params: Any) -> Any:
        return self.client.call(method, team=bench.team.name, **params)

    def info(self, bench: Bench) -> DeployInfo:
        data = self._call(bench, "press.api.bench.deploy_information", name=bench.name)
        return parse_deploy_info(data, bench)

    def plan(
        self, info: DeployInfo, apps: Sequence[str] | None, sites: Sequence[str]
    ) -> DeployPlan:
        """Validate the names and build the plan. `apps=None` means every update."""
        updates = {app.app: app for app in info.updates}
        if apps is None:
            chosen = list(info.updates)
        else:
            unknown = [name for name in apps if name not in updates]
            if unknown:
                offered = ", ".join(updates) or "none"
                raise UsageError(
                    f"No update to deploy for app {', '.join(unknown)} on bench {info.bench.name}",
                    hint=f"Apps with an update: {offered}",
                )
            chosen = [updates[name] for name in dict.fromkeys(apps)]
        if not chosen and not info.removed_apps:
            raise UsageError(
                f"No app selected for bench {info.bench.name}",
                hint="Select at least one app to deploy.",
            )
        by_name = {site.name: site for site in info.sites}
        unknown_sites = [name for name in sites if name not in by_name]
        if unknown_sites:
            listed = ", ".join(by_name) or "none"
            raise UsageError(
                f"Site {', '.join(unknown_sites)} is not on bench {info.bench.name}",
                hint=f"Sites on this bench: {listed}",
            )
        return DeployPlan(
            bench=info.bench,
            apps=chosen,
            sites=[by_name[name] for name in dict.fromkeys(sites)],
            removed_apps=list(info.removed_apps),
            last_build=info.last_build,
        )

    def start(self, plan: DeployPlan) -> str:
        """The only write: send the deploy. Returns the FC reference (pipeline or build)."""
        ref = self.client.write(DEPLOY_METHOD, team=plan.bench.team.name, **plan.payload())
        return _str(ref)

    def build(self, bench: Bench, name: str) -> DeployState:
        data = self._call(bench, "press.api.client.get", doctype=BUILD_DOCTYPE, name=name)
        return parse_build(data)

    def state(self, bench: Bench) -> DeployState:
        """The current deploy state of the bench (for `fcm bench-show`)."""
        status = self._call(bench, "press.api.bench.deploy_status", name=bench.name) or {}
        build = _str(status.get("candidate")) if isinstance(status, dict) else ""
        if build:
            return self.build(bench, build)
        if isinstance(status, dict) and status.get("is_validating"):
            return DeployState(stage="validating")
        return DeployState(stage="idle")

    def watch(
        self,
        plan: DeployPlan,
        sleep: Callable[[float], None],
        poll_seconds: float = POLL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> Iterator[DeployState]:
        """Follow the deploy of `plan` until it ends. Yield one state after every poll that
        FC answered, also when nothing changed, so the caller can show that FC answers.
        `checked_at` is the `clock()` time of that answer.

        Raises DeployFailed when the build fails, or when FC ends the deploy before a
        build starts."""
        bench = plan.bench
        build = ""
        idle_polls = 0
        polls = 0

        def answered(state: DeployState) -> DeployState:
            nonlocal polls
            polls += 1
            return replace(state, checked_at=clock(), polls=polls)

        while True:
            status = self._call(bench, "press.api.bench.deploy_status", name=bench.name) or {}
            build = _str(status.get("candidate")) or build
            if not build and not status.get("is_validating"):
                # No pipeline: either the old deploy flow, or FC ended the deploy early.
                info = self.info(bench)
                if info.last_build and info.last_build != plan.last_build:
                    build = info.last_build
            if build:
                state = self.build(bench, build)
                if state.stage == "failure":
                    yield answered(state)
                    step = state.failed_step
                    raise DeployFailed(
                        f"The deploy failed on FC at {step.label if step else 'the build'}",
                        step=step.label if step else None,
                        target=f"bench {bench.name}",
                        server_message=state.message or None,
                        hint=f"Run: fcm bench-show {bench.name}",
                    )
                if state.stage == "finishing":
                    break
                yield answered(state)
            elif status.get("is_validating"):
                yield answered(DeployState(stage="validating"))
            else:
                idle_polls += 1
                if idle_polls >= IDLE_POLLS_LIMIT:
                    raise DeployFailed(
                        "FC ended the deploy before a build started",
                        target=f"bench {bench.name}",
                        hint="Check the deploy in the FC dashboard.",
                    )
                yield answered(DeployState(stage="starting"))
            sleep(poll_seconds)

        # The build succeeded. FC now creates the new bench.
        build_state = self.build(bench, build)
        done_steps = build_state.steps
        finishing = DeployState(stage="finishing", build=build, status="Success", steps=done_steps)
        while True:
            yield answered(finishing)
            info = self.info(bench)
            if not info.busy:
                break
            sleep(poll_seconds)

        # Then FC moves each selected site in a separate job. No busy flag covers that job,
        # so wait until each site is on a bench other than the one it had before the deploy.
        old = {site.name: site.bench for site in plan.sites}
        started = clock()
        while True:
            now = {site.name: site.bench for site in info.sites}
            moved = tuple((name, now.get(name, before) != before) for name, before in old.items())
            if all(flag for _, flag in moved):
                break
            if clock() - started >= SITE_UPDATE_LIMIT_SECONDS:
                waiting = [name for name, flag in moved if not flag]
                raise SiteUpdateUnknown(
                    "The bench was deployed, but FC did not confirm the update of "
                    + ", ".join(waiting)
                    + f" in {SITE_UPDATE_LIMIT_SECONDS // 60} minutes. Its result is not known.",
                    target=f"bench {bench.name}",
                    hint=f"Check the site in the FC dashboard. Run: fcm bench-show {bench.name}",
                )
            yield answered(
                DeployState(
                    stage="updating_sites",
                    build=build,
                    status="Success",
                    steps=done_steps,
                    sites=moved,
                )
            )
            sleep(poll_seconds)
            info = self.info(bench)

        yield answered(
            DeployState(
                stage="success", build=build, status="Success", steps=done_steps, sites=moved
            )
        )
