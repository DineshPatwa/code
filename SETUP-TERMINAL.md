# 🖥️ Connect the in-browser terminal to your cloud VM

The lab page has an **“Open terminal”** button. It embeds a terminal served by
[`ttyd`](https://github.com/tsl0922/ttyd) running on your own cloud VM. You type,
it runs on your real server.

This guide covers the **easy + secure** setup for personal use: run `ttyd` bound
to `localhost` on the VM, then reach it through an **SSH tunnel**. Nothing is
exposed to the public internet.

---

## 1. Install `ttyd` on your VM

SSH into your VM, then install `ttyd`:

**Ubuntu / Debian**
```bash
sudo apt update && sudo apt install -y ttyd
```

**RHEL / Rocky / Alma / Fedora**
```bash
sudo dnf install -y ttyd     # or: sudo yum install -y ttyd
```

**If it's not in your repos**, grab a static binary:
```bash
sudo wget -O /usr/local/bin/ttyd \
  https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64
sudo chmod +x /usr/local/bin/ttyd
```

Verify:
```bash
ttyd --version
```

---

## 2. Run `ttyd` (bound to localhost only)

```bash
ttyd -i 127.0.0.1 -p 7681 -W bash
```

- `-i 127.0.0.1` → only listens on localhost (not reachable from the internet ✅)
- `-p 7681` → port
- `-W` → allow **write** (interactive typing). Drop `-W` for a read-only terminal.
- `bash` → the shell/command to run

> Leave this running in the SSH session (or use `tmux`/`screen`/a systemd service
> so it survives disconnects — see the bottom of this file).

---

## 3. Tunnel the port to your PC over SSH

In a terminal on **this Windows PC** (PowerShell has `ssh` built in):

```powershell
ssh -N -L 7681:localhost:7681 user@YOUR_VM_IP
```

- `-N` → don't open a shell, just forward the port
- `-L 7681:localhost:7681` → local port 7681 → VM's localhost:7681

Keep this window open while you practice.

---

## 4. Connect the site

1. Open a lab (e.g. `index.html` → **Try a sample lab**).
2. Click **💻 Open terminal**.
3. In the panel, enter:
   ```
   http://localhost:7681
   ```
4. Click **Connect**. The live terminal loads in the split panel. 🎉

The URL is remembered in your browser, so you only enter it once.

---

## Alternative: expose ttyd directly (less secure)

If you don't want an SSH tunnel and understand the risk, you can bind ttyd to all
interfaces **with a password**:

```bash
ttyd -p 7681 -W -c myuser:mypassword bash
```

Then connect the site to `http://YOUR_VM_IP:7681`.

⚠️ **Anyone who reaches that port + password gets a shell on your VM.** At minimum:
- always set `-c user:pass`
- lock the port to your IP in the cloud firewall / security group
- ideally put it behind HTTPS (e.g. a reverse proxy with TLS)

The SSH-tunnel method (steps 1–4) avoids all of this and is recommended.

---

## Keep ttyd running after you log out (optional)

**Quick way — tmux:**
```bash
tmux new -s ttyd
ttyd -i 127.0.0.1 -p 7681 -W bash
# detach with Ctrl-b then d ; reattach with: tmux attach -t ttyd
```

**Proper way — systemd service** (`/etc/systemd/system/ttyd.service`):
```ini
[Unit]
Description=ttyd web terminal
After=network.target

[Service]
ExecStart=/usr/local/bin/ttyd -i 127.0.0.1 -p 7681 -W bash
Restart=always
User=YOUR_USER

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ttyd
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Panel is blank / won't load | Is the SSH tunnel running? Is `ttyd` running on the VM? |
| "Connection refused" | Wrong port, or ttyd not started. Re-run step 2 & 3. |
| Terminal loads but can't type | You forgot `-W` on the `ttyd` command. |
| Works then dies on logout | Use tmux or the systemd service above. |
| Serving site over HTTPS later | Terminal must also be HTTPS (no mixed content). Use a TLS reverse proxy. |
