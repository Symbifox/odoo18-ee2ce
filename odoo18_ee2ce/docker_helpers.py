"""Docker CLI helpers used by the migration pipeline."""

import re
import subprocess


def docker_exec(container, cmd, check=True, timeout=600):
    """Run a command inside a Docker container and return stdout.

    Args:
        container: Container name or ID.
        cmd: Either a string (run via `bash -c`) or a list of args.
        check: Raise RuntimeError on non-zero exit.
        timeout: Seconds before subprocess.TimeoutExpired.
    """
    full = ["docker", "exec", container] + (["bash", "-c", cmd] if isinstance(cmd, str) else cmd)
    r = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"docker exec failed (rc={r.returncode}): {r.stderr[:300]}")
    return r.stdout.strip()


def get_db_host(db_container):
    """Auto-detect the DB container's IP on the Docker network."""
    try:
        ip = docker_exec(db_container, "hostname -i", check=False)
        if ip and re.match(r"[\d.]+", ip):
            return ip.split()[0]
    except Exception:
        pass
    # Fallback: inspect Docker network
    r = subprocess.run(
        ["docker", "inspect", db_container,
         "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}"],
        capture_output=True, text=True,
    )
    ip = r.stdout.strip()
    if ip:
        return ip
    return "localhost"
