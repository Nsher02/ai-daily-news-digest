"""Block direct pushes and deletions to main in checkouts with the hook installed."""
import sys


def main():
    for line in sys.stdin:
        fields = line.split()
        if len(fields) != 4:
            print('Push stopped: cannot validate the destination ref.', file=sys.stderr)
            return 1
        if fields[2] == 'refs/heads/main':
            print('Direct pushes to main are blocked locally. Open a PR and use python3 scripts/merge_pr.py NUMBER after tests pass.', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
