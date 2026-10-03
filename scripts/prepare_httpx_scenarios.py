from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTBED = ROOT / ".httpx-testbed"
PIN_FILE = ROOT / "evals" / "httpx" / "PINNED_COMMIT.txt"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def commit_scenario(destination: Path, scenario: int, base: str) -> str:
    subprocess.run(["git", "clone", "--shared", "--no-hardlinks", "--quiet", str(TESTBED), str(destination)], check=True)
    git(destination, "checkout", "-q", "-b", f"codex/eval-scenario-{scenario}", base)
    git(destination, "config", "user.name", "DocSync Evaluation")
    git(destination, "config", "user.email", "docsync-eval@localhost")
    config_path = destination / "httpx" / "_config.py"
    source = config_path.read_text(encoding="utf-8")
    if scenario == 1:
        source = source.replace("DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)", "DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=8.0)", 1)
    elif scenario == 2:
        before = """    def as_dict(self) -> dict[str, float | None]:
        return {
            "connect": self.connect,
            "read": self.read,
            "write": self.write,
            "pool": self.pool,
        }
"""
        after = """    def as_dict(self) -> dict[str, float | None]:
        names = ("connect", "read", "write", "pool")
        values = (self.connect, self.read, self.write, self.pool)
        return {name: value for name, value in zip(names, values)}
"""
        if before not in source:
            raise RuntimeError("Pinned HTTPX source no longer matches the Scenario 2 fixture")
        source = source.replace(before, after, 1)
    elif scenario == 3:
        anchor = """        return {
            "connect": self.connect,
            "read": self.read,
            "write": self.write,
            "pool": self.pool,
        }
"""
        addition = anchor + """
    @property
    def is_disabled(self) -> bool:
        return all(value is None for value in self.as_dict().values())
"""
        if anchor not in source:
            raise RuntimeError("Pinned HTTPX source no longer matches the Scenario 3 fixture")
        source = source.replace(anchor, addition, 1)
    elif scenario == 4:
        source = "from external_runtime_policy import timeout_seconds\n" + source
        source = source.replace("DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=5.0)", "DEFAULT_TIMEOUT_CONFIG = Timeout(timeout=timeout_seconds())", 1)
    else:
        raise ValueError(scenario)
    if source == config_path.read_text(encoding="utf-8"):
        raise RuntimeError(f"Scenario {scenario} fixture did not change the source")
    config_path.write_text(source, encoding="utf-8", newline="")
    git(destination, "add", "httpx/_config.py")
    git(destination, "commit", "-q", "-m", f"Evaluation scenario {scenario}")
    return git(destination, "rev-parse", "HEAD")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create isolated, local HTTPX evaluation commits")
    parser.add_argument("--output", type=Path, default=ROOT / ".httpx-scenarios")
    args = parser.parse_args()
    base = PIN_FILE.read_text(encoding="utf-8").strip()
    actual = git(TESTBED, "rev-parse", "HEAD")
    if actual != base:
        raise SystemExit(f"HTTPX testbed is at {actual}, expected pinned commit {base}")
    args.output.mkdir(parents=True, exist_ok=True)
    scenarios = [
        (1, "Default timeout changes from five to eight seconds", "UPDATE", "httpx/_config.py::DEFAULT_TIMEOUT_CONFIG", ["docs/advanced/timeouts.md::__intro__", "docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client", "docs/quickstart.md::timeouts"]),
        (2, "Internal Timeout.as_dict refactor preserves behavior", "NO_CHANGE", "httpx/_config.py::Timeout.as_dict", ["docs/advanced/timeouts.md::fine-tuning-the-configuration"]),
        (3, "Timeout.is_disabled public property added", "UPDATE", "httpx/_config.py::Timeout.is_disabled", ["docs/advanced/timeouts.md::setting-and-disabling-timeouts"]),
        (4, "Default timeout comes from an unavailable external runtime policy", "UNCERTAIN", "httpx/_config.py::DEFAULT_TIMEOUT_CONFIG", ["docs/advanced/timeouts.md::__intro__", "docs/advanced/timeouts.md::setting-a-default-timeout-on-a-client", "docs/quickstart.md::timeouts"]),
    ]
    manifest = []
    for number, description, expected, code_id, section_ids in scenarios:
        destination = args.output / f"scenario-{number}-repo"
        if destination.exists():
            raise SystemExit(f"Refusing to overwrite existing scenario repo: {destination}")
        new_sha = commit_scenario(destination, number, base)
        manifest.append({
            "scenario": number, "description": description, "expected_decision": expected,
            "repo": str(destination.resolve()), "old_sha": base, "new_sha": new_sha,
            "code_id": code_id, "section_ids": section_ids,
        })
        print(f"Scenario {number}: {new_sha} ({expected}) {destination}")
    output_file = args.output / "manifest.json"
    output_file.write_text(json.dumps({"pinned_base": base, "scenarios": manifest}, indent=2), encoding="utf-8")
    print(f"Manifest: {output_file}")


if __name__ == "__main__":
    main()

