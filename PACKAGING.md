# Publishing Yaz

Three ways users can install Yaz, ordered by how much work *you* have to do:

1. **Download `.deb` from GitHub Releases** — Build today, paste a URL.
2. **`apt install` via Launchpad PPA** — 1-day setup, one-time GPG dance.
3. **Snap Store (Ubuntu App Center)** — 1–2 day review, ongoing maintenance.

---

## 1. Ship a `.deb` via GitHub Releases (today)

### Build it

```bash
./build_deb.sh 0.1.1
```

You'll get `yaz-screenshot_0.1.1_all.deb` in the project root (≈29 KB).

### Test it locally

```bash
sudo apt install ./yaz-screenshot_0.1.1_all.deb       # apt resolves the python3-pyqt6 etc deps
# or
sudo dpkg -i yaz-screenshot_0.1.1_all.deb && sudo apt -f install
```

To uninstall: `sudo apt remove yaz-screenshot`.

### Publish

1. Go to your GitHub repo → **Releases** → **Draft a new release**.
2. Tag: `v0.1.1`, title: `Yaz 0.1.1`.
3. Drag the `.deb` into the assets area.
4. Publish.

Users then install with:

```bash
wget https://github.com/yetesfa/yaz/releases/download/v0.1.1/yaz-screenshot_0.1.1_all.deb
sudo apt install ./yaz-screenshot_0.1.1_all.deb
```

The package also ships AppStream metadata, so it appears in **GNOME Software**
under Graphics → Yaz once installed (or after they run `apt update` if from a
repo).

---

## 2. Launchpad PPA — `apt install yaz-screenshot` for everyone

This is what lets users do:

```bash
sudo add-apt-repository ppa:yetesfa/yaz
sudo apt update
sudo apt install yaz-screenshot
```

### One-time setup (≈1 hour, only you do this)

1. **Make a Launchpad account**: <https://launchpad.net/+login>.
   Use the same email as your GPG key.
2. **Generate a GPG key** (skip if you already have one):

   ```bash
   gpg --full-generate-key            # pick RSA 4096, your real email
   gpg --list-secret-keys --keyid-format=long
   ```

   Note the long key ID (the part after `rsa4096/`).
3. **Upload the public key** to a public keyserver:

   ```bash
   gpg --send-keys <KEYID>
   ```

4. On <https://launchpad.net/~yetesfa/+editpgpkeys>, paste the fingerprint
   from `gpg --fingerprint <KEYID>` and confirm via the email Launchpad sends.

5. **Create a PPA** on Launchpad: visit
   <https://launchpad.net/~yetesfa> → *Create a new PPA*. Call it `yaz`.

6. **Install build tools locally**:

   ```bash
   sudo apt install devscripts dput debhelper dh-python build-essential
   ```

7. **Replace placeholders** in `debian/changelog` (replace
   `noreply@example.com` with your real email — must match your GPG key).

### Each release

```bash
# 1. Build a SIGNED source package (signs with your GPG key)
debuild -S -sa

# 2. Files appear one directory up:
ls ../yaz-screenshot_0.1.1*

# 3. Upload to your PPA
dput ppa:yetesfa/yaz ../yaz-screenshot_0.1.1_source.changes
```

Launchpad will email you when the build succeeds (≈10–30 min). After that,
anyone can:

```bash
sudo add-apt-repository ppa:yetesfa/yaz
sudo apt update
sudo apt install yaz-screenshot
```

Future updates: bump the version in `debian/changelog` (`dch -i`) and rerun
`debuild -S -sa && dput …`.

---

## 3. Snap Store (Ubuntu App Center)

Visible to every Ubuntu 24.04+ user in the **App Center** when they search.

### Build a snap locally

```bash
sudo snap install snapcraft --classic
snapcraft
# Produces yaz-screenshot_0.1.1_amd64.snap
sudo snap install --dangerous ./yaz-screenshot_0.1.1_amd64.snap   # test before publishing
```

### Publish to the store

1. Create a developer account: <https://snapcraft.io/account>.
2. Register the snap name (one-time):

   ```bash
   snapcraft login
   snapcraft register yaz-screenshot   # matches the .deb / PPA name; "yaz" is taken upstream
   ```

3. Upload + release:

   ```bash
   snapcraft upload --release=stable yaz-screenshot_0.1.1_amd64.snap
   ```

4. Canonical reviews snaps that need the `personal-files` plug (Yaz needs
   it to write `~/.config/Yaz/`). Expect a 1–2 day automated/manual review
   — answer any questions on the review thread.

5. Once approved, it shows up in `snap find yaz-screenshot` and Ubuntu App Center.

### Caveat: snap sandboxing

Yaz inside a snap can't shell out to the user's `gnome-screenshot` binary —
the sandbox blocks it. The snapcraft.yaml stages its own copy, but the
**Wayland screenshot portal** path is the one that consistently works for
sandboxed apps. Test all capture modes after `snap install --dangerous` and
file any portal issues against `xdg-desktop-portal`.

---

## 4. Flathub (cross-distro)

Flathub gives you reach to Fedora, OpenSUSE, Arch (and any other distro with
Flatpak installed). Review is stricter (manual) and takes weeks. Skip for
v0.1 — revisit once you have stars/users.

When you're ready: <https://docs.flathub.org/docs/for-app-authors/submission>.

---

## 5. Official Ubuntu / Debian archive

Path: package for Debian first (Debian Mentors process, find a sponsor),
get it into Debian unstable, then it auto-syncs to Ubuntu universe a few
months later. Realistic timeline: 6–12 months. Worth it once Yaz has
real users.

Reference: <https://mentors.debian.net/intro-maintainers/>.

---

## TL;DR — what to do this week

1. `./build_deb.sh` → upload `.deb` to **GitHub Releases**.
2. Open a Launchpad account, set up the PPA, run `debuild -S -sa && dput`.
3. Run `snapcraft` and submit to the **Snap Store**.

Now your README's install matrix can say:

```bash
# Option A — direct .deb
wget …yaz-screenshot_0.1.1_all.deb && sudo apt install ./yaz-screenshot_0.1.1_all.deb

# Option B — PPA
sudo add-apt-repository ppa:yetesfa/yaz && sudo apt install yaz-screenshot

# Option C — snap
sudo snap install yaz-screenshot
```
