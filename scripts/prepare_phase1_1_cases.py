from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evals" / "phase1_1" / "heldout_manifest.json"
CASES_ROOT = ROOT / ".httpx-scenarios" / "phase1-1"

CODE = {
    "H1": (
        "def display_title(value):\n    return value\n",
        "def display_title(value):\n    return value.strip().title()\n",
    ),
    "H2": (
        "def protocol_version():\n    return 'v1'\n",
        "def protocol_version():\n    return 'v2'\n",
    ),
    "H3": (
        "def normalize_name(value):\n    return value.strip().lower()\n",
        "def normalize_name(value):\n    value = value.strip()\n    return value.lower()\n",
    ),
    "H4": (
        "def max_attempts():\n    return 3\n",
        "def max_attempts():\n    attempts = 3\n    return attempts\n",
    ),
    "H5": (
        "def is_eligible(item):\n    return bool(item.get('active', False))\n",
        "def is_eligible(item):\n    return eligibility_policy.allows(item)\n",
    ),
    "H6": (
        "def worker_count():\n    return 4\n",
        "def worker_count():\n    return deployment_config['workers']\n",
    ),
    "H7": (
        "def can_retry(response):\n    return response.status_code in {408, 429} or response.status_code >= 500\n",
        "def can_retry(response, client):\n    return client.retry_provider.is_retryable(response)\n",
    ),
    "H8": (
        "def open_session(host):\n    return socket.create_connection(host)\n",
        "def open_session(host, session_manager):\n    return session_manager.open(host)\n",
    ),
    "H9": (
        "def retention_days():\n    return 30\n",
        "import os\n\ndef retention_days():\n    return int(os.environ['RETENTION_DAYS'])\n",
    ),
    "H10": (
        "def preferred_protocol(supported_protocols):\n    return 'h2' if {'h2', 'http/1.1'} <= set(supported_protocols) else 'http/1.1'\n",
        "def preferred_protocol(supported_protocols):\n    return runtime_profile.alpn_protocols(supported_protocols)\n",
    ),
    "H11": (
        "def should_encrypt(record):\n    return record.get('sensitive', False)\n",
        "def should_encrypt(record):\n    return crypto_provider.requires_encryption(record)\n",
    ),
}


def run(repo: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")


def write(repo: Path, relative: str, text: str) -> None:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    output = CASES_ROOT / "generated-manifest.json"
    generated: dict[str, dict[str, str]] = (
        json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    )
    for case in manifest["cases"]:
        case_id = case["scenario_id"]
        repo = CASES_ROOT / case_id
        if repo.exists():
            if case_id in generated:
                continue
            raise SystemExit(f"Refusing to overwrite untracked held-out repository: {repo}")
        repo.mkdir(parents=True)
        run(repo, "init", "--quiet")
        run(repo, "config", "user.name", "DocSync Phase 1.1 Evaluation")
        run(repo, "config", "user.email", "docsync-eval@example.invalid")
        old_code, new_code = CODE[case_id]
        write(repo, "scenario.py", old_code)
        doc = f"# Controlled behavior\n\n## {case['section_heading']}\n\n{case['documentation']}\n"
        write(repo, "docs/behavior.md", doc)
        run(repo, "add", "scenario.py", "docs/behavior.md")
        run(repo, "commit", "--quiet", "-m", f"{case_id}: initial documented behavior")
        old_sha = run_output(repo, "rev-parse", "HEAD")
        write(repo, "scenario.py", new_code)
        run(repo, "add", "scenario.py")
        run(repo, "commit", "--quiet", "-m", f"{case_id}: controlled behavior change")
        new_sha = run_output(repo, "rev-parse", "HEAD")
        generated[case_id] = {
            "repo": str(repo.resolve()),
            "old_sha": old_sha,
            "new_sha": new_sha,
        }

    output.write_text(json.dumps(generated, indent=2), encoding="utf-8")
    portable = {
        scenario_id: {
            **refs,
            "repo": str(Path(refs["repo"]).resolve().relative_to(ROOT)),
        }
        for scenario_id, refs in generated.items()
    }
    portable_output = ROOT / "evals" / "phase1_1" / "fixture_commits.json"
    portable_output.write_text(json.dumps(portable, indent=2), encoding="utf-8")
    print(f"Prepared {len(generated)} held-out repositories under {CASES_ROOT}")
    print(f"Generated commit manifest: {output}")
    print(f"Portable fixture manifest: {portable_output}")


def run_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


if __name__ == "__main__":
    main()
