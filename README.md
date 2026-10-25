# persona-lock

Block distracting websites on your Mac.

`plock` adds blocked sites to a clearly marked section of `/etc/hosts`, so they
won't load in any browser. Unblocking asks you to type out a confirmation, a
small speed bump to make you think twice.

## Install

```bash
pipx install -e .
```

(or `pip install -e .`, or run `python3 persona_lock.py` directly)

## Usage

```bash
plock add reddit.com youtube.com   # block (www. is covered too)
plock list                         # show what's blocked
plock remove reddit.com            # unblock, after typing "unblock reddit.com"
plock sync                         # re-apply if /etc/hosts was reset (e.g. by a macOS update)
```

Editing `/etc/hosts` needs admin rights, so `plock` will ask for your password
via `sudo` when it changes the file. Run it as yourself, not with `sudo plock`.

If a blocked site still loads, restart the browser. Browsers cache DNS
lookups and keep existing connections open.

## How it works

- Your blocklist lives in `~/.config/persona-lock/blocklist.txt`.
- Each blocked domain (plus `www.`, `m.` and `mobile.`) points to `0.0.0.0` / `::`
  in a section of `/etc/hosts` between `# >>> persona-lock >>>` and
  `# <<< persona-lock <<<`. Nothing else in the file is touched.
- Popular sites that span several domains are blocked as a group: blocking
  `x.com` also blocks `twitter.com`, `t.co`, `twimg.com` and its APIs. Without
  this, a site's cached app can keep working. See `SITE_GROUPS` in
  `persona_lock.py`.
- After changing the file, `plock` flushes the macOS DNS cache.

## Development

```bash
python3 -m unittest -v
```

`PERSONA_LOCK_HOSTS` and `PERSONA_LOCK_CONFIG` point the tool at a different
hosts file and config directory, which is handy for trying it out safely.
