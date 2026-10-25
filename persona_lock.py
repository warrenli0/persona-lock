"""persona-lock: block websites on macOS by managing a section of /etc/hosts."""

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HOSTS_PATH = Path(os.environ.get("PERSONA_LOCK_HOSTS", "/etc/hosts"))
CONFIG_DIR = Path(
    os.environ.get("PERSONA_LOCK_CONFIG", Path.home() / ".config" / "persona-lock")
)
BLOCKLIST_PATH = CONFIG_DIR / "blocklist.txt"

BEGIN_MARKER = "# >>> persona-lock >>>"
END_MARKER = "# <<< persona-lock <<<"

COMMON_SUBDOMAINS = ("www", "m", "mobile")

# Popular sites spread over several domains (APIs, CDNs, short links). Without
# these, a site's cached app shell can keep working even with its main domain
# blocked. Blocking any domain in a group blocks the whole group.
SITE_GROUPS = [
    ["x.com", "twitter.com", "t.co", "twimg.com", "api.x.com", "api.twitter.com",
     "abs.twimg.com", "pbs.twimg.com", "video.twimg.com"],
    ["reddit.com", "redd.it", "redditmedia.com", "redditstatic.com",
     "old.reddit.com", "new.reddit.com", "i.redd.it", "v.redd.it"],
    ["youtube.com", "youtu.be", "youtube-nocookie.com", "ytimg.com", "i.ytimg.com",
     "music.youtube.com"],
    ["instagram.com", "cdninstagram.com", "i.instagram.com"],
    ["facebook.com", "fb.com", "messenger.com", "fbcdn.net", "static.xx.fbcdn.net"],
    ["tiktok.com", "tiktokv.com", "tiktokcdn.com"],
]

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def normalize_domain(raw):
    """Turn 'https://www.Reddit.com/r/foo' into 'reddit.com'."""
    domain = raw.strip().lower()
    domain = re.sub(r"^[a-z]+://", "", domain)
    domain = domain.split("/", 1)[0].split(":", 1)[0]
    domain = domain.removeprefix("www.").rstrip(".")
    if not DOMAIN_RE.match(domain):
        raise ValueError(f"not a valid domain: {raw!r}")
    return domain


def load_blocklist():
    if not BLOCKLIST_PATH.exists():
        return []
    lines = BLOCKLIST_PATH.read_text().splitlines()
    return sorted({line.strip() for line in lines if line.strip() and not line.startswith("#")})


def save_blocklist(domains):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    BLOCKLIST_PATH.write_text("".join(f"{d}\n" for d in sorted(set(domains))))


def expand_hosts(domains):
    """Every hostname to block for the given domains, in a stable order."""
    hosts = {}
    for domain in domains:
        group = next((g for g in SITE_GROUPS if domain in g), [domain])
        for name in [domain, *group]:
            hosts[name] = None
            for sub in COMMON_SUBDOMAINS:
                hosts[f"{sub}.{name}"] = None
    return list(hosts)


def render_block(domains):
    """The managed section of the hosts file, or '' if nothing is blocked."""
    if not domains:
        return ""
    lines = [BEGIN_MARKER, "# Managed by persona-lock. Edit with `plock`, not by hand."]
    for host in expand_hosts(domains):
        lines.append(f"0.0.0.0 {host}")
        lines.append(f":: {host}")
    lines.append(END_MARKER)
    return "\n".join(lines) + "\n"


def strip_block(hosts_text):
    """Remove any existing persona-lock section from the hosts file text."""
    # Also eat the blank line build_hosts puts before the section, so
    # adding then removing everything leaves the file byte-for-byte unchanged.
    pattern = re.compile(
        rf"\n?{re.escape(BEGIN_MARKER)}.*?{re.escape(END_MARKER)}\n?", re.DOTALL
    )
    return pattern.sub("", hosts_text)


def build_hosts(hosts_text, domains):
    base = strip_block(hosts_text)
    block = render_block(domains)
    if not block:
        return base
    if base and not base.endswith("\n"):
        base += "\n"
    return f"{base}\n{block}"


def write_hosts(new_text):
    """Write the hosts file, using sudo only when we can't write it ourselves."""
    if os.access(HOSTS_PATH, os.W_OK):
        HOSTS_PATH.write_text(new_text)
        return

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".hosts") as tmp:
        tmp.write(new_text)
    try:
        print(f"Updating {HOSTS_PATH} (you may be asked for your password)...")
        # `cp` onto the existing file keeps its owner and permissions.
        subprocess.run(["sudo", "cp", tmp.name, str(HOSTS_PATH)], check=True)
        subprocess.run(["sudo", "dscacheutil", "-flushcache"], check=False)
        subprocess.run(["sudo", "killall", "-HUP", "mDNSResponder"], check=False)
    finally:
        os.unlink(tmp.name)


def apply(domains):
    current = HOSTS_PATH.read_text()
    updated = build_hosts(current, domains)
    if updated != current:
        write_hosts(updated)


def confirm_unblock(domain):
    """A small speed bump: make the user spell out what they're doing."""
    print(f"You blocked {domain} for a reason.")
    phrase = f"unblock {domain}"
    try:
        answer = input(f"Type '{phrase}' to confirm: ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() == phrase


def cmd_add(args):
    try:
        new = [normalize_domain(d) for d in args.domains]
    except ValueError as e:
        sys.exit(f"error: {e}")
    blocked = load_blocklist()
    added = [d for d in new if d not in blocked]
    if not added:
        print("Already blocked.")
        return
    domains = sorted(set(blocked) | set(added))
    apply(domains)
    save_blocklist(domains)
    for d in added:
        print(f"Blocked {d}")
    print(
        "If a blocked site still loads, fully quit and reopen your browser "
        "(Cmd+Q) so it drops cached connections."
    )


def cmd_remove(args):
    try:
        targets = [normalize_domain(d) for d in args.domains]
    except ValueError as e:
        sys.exit(f"error: {e}")
    blocked = load_blocklist()
    removed = []
    for domain in targets:
        if domain not in blocked:
            print(f"{domain} isn't blocked.")
        elif args.yes or confirm_unblock(domain):
            removed.append(domain)
        else:
            print(f"Kept {domain} blocked.")
    if not removed:
        return
    domains = [d for d in blocked if d not in removed]
    apply(domains)
    save_blocklist(domains)
    for d in removed:
        print(f"Unblocked {d}")


def cmd_list(args):
    blocked = load_blocklist()
    if not blocked:
        print("Nothing is blocked.")
    for d in blocked:
        print(d)


def cmd_sync(args):
    """Re-write /etc/hosts from the blocklist, e.g. after a macOS update resets it."""
    apply(load_blocklist())
    print("Hosts file is in sync with the blocklist.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="plock", description="Block websites on this Mac.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="block one or more websites")
    p.add_argument("domains", nargs="+")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("remove", help="unblock websites (asks you to confirm)")
    p.add_argument("domains", nargs="+")
    p.add_argument("-y", "--yes", action="store_true", help="skip the confirmation")
    p.set_defaults(func=cmd_remove)

    p = sub.add_parser("list", help="show blocked websites")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("sync", help="re-apply the blocklist to the hosts file")
    p.set_defaults(func=cmd_sync)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
