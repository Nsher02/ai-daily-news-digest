"""Run a checksum-pinned free Gitleaks CLI; never echo scanner output or secrets."""
import argparse
import hashlib
import io
import platform
from pathlib import Path
import subprocess
import tarfile
import tempfile


VERSION = '8.30.1'
# Official release checksums, pinned for review rather than downloaded as trust at runtime.
CHECKSUMS = {
    ('Darwin', 'arm64'): ('darwin_arm64', 'b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5'),
    ('Darwin', 'x86_64'): ('darwin_x64', 'dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709'),
    ('Linux', 'x86_64'): ('linux_x64', '551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb'),
    ('Linux', 'aarch64'): ('linux_arm64', 'e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080'),
}


def install(directory):
    """Authenticate the archive, then extract only its regular executable member."""
    target = CHECKSUMS.get((platform.system(), platform.machine()))
    if target is None:
        raise ValueError('Unsupported platform; use macOS or Linux with x64/ARM64.')
    archive_name = f'gitleaks_{VERSION}_{target[0]}.tar.gz'
    url = f'https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}/{archive_name}'
    response = subprocess.run(
        ['curl', '--fail', '--silent', '--show-error', '--location', '--max-time', '90', url],
        capture_output=True, timeout=100,
    )
    if response.returncode != 0:
        raise ValueError('Could not download the pinned Gitleaks release; scan did not run.')
    if hashlib.sha256(response.stdout).hexdigest() != target[1]:
        raise ValueError('Gitleaks archive checksum mismatch; refusing execution.')
    with tarfile.open(fileobj=io.BytesIO(response.stdout), mode='r:gz') as archive:
        member = archive.getmember('gitleaks')
        if not member.isfile() or member.size > 100_000_000:
            raise ValueError('Invalid executable in Gitleaks archive.')
        content = archive.extractfile(member).read()
    binary = Path(directory) / 'gitleaks'
    binary.write_bytes(content)
    binary.chmod(0o700)
    return binary


def scan(repository, binary, staged=False):
    flags = ['--redact=100', '--no-banner', '--no-color', '--log-level', 'error', '--timeout', '120']
    if staged:
        diff = subprocess.run(
            ['git', 'diff', '--cached', '--no-ext-diff', '--no-textconv', '--unified=0'],
            cwd=repository, capture_output=True, timeout=30,
        )
        if diff.returncode:
            raise ValueError('Could not read staged changes; scan did not run.')
        additions = b'\n'.join(line[1:] for line in diff.stdout.splitlines()
                                if line.startswith(b'+') and not line.startswith(b'+++ '))
        if not additions:
            print('Gitleaks: no staged changes to scan.')
            return 0
        command = [str(binary), 'stdin', *flags]
        payload = additions
    else:
        command = [str(binary), 'git', '--log-opts=--all', *flags]
        payload = None
    # Even redacted raw findings can contain source context; never forward stdout/stderr.
    result = subprocess.run(command, input=payload, cwd=repository, capture_output=True, timeout=150)
    if result.returncode == 0:
        print('Gitleaks: scan passed.')
        return 0
    if result.returncode == 1:
        print('Gitleaks: potential secrets detected; commit/merge blocked. Raw findings are suppressed.')
        return 1
    raise ValueError('Gitleaks could not complete; commit/merge blocked. Raw diagnostics are suppressed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='scan only staged changes before committing')
    args = parser.parse_args()
    try:
        with tempfile.TemporaryDirectory(prefix='digest-gitleaks-') as directory:
            return scan(Path.cwd(), install(directory), args.staged)
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.SubprocessError):
        print('Gitleaks: scan failed or could not complete; commit/merge blocked. Check installation and run locally.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
