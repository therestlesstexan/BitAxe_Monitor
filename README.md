# 📟 Bitaxe Flatline Monitor

**Version:** `v0.13`  
**Author:** You  
**Language:** Python 3  
**Purpose:** Monitors one or more Bitaxe miners and restarts them if shares stop increasing. Logs activity and sends alerts via Discord.

## 🛠️ Features

- 🔁 Auto-Restart for inactive Bitaxe miners
- 🧵 Multi-miner support via config file
- 📝 Daily rotated logs (per miner)
- 🗜️ Gzip compression for old logs
- 🧹 Auto-delete logs older than `max_days`
- 📡 Discord alerts for:
  - Startup summary
  - No-share restarts
  - Device unreachable
  - Restart failures

## ⚡ Requirements

- Python 3.6+
- `requests` (install via pip)

## 🚀 Quick Start

```bash
python3 bitaxe_monitor.py -c bitaxe_monitor.conf
```

## 🔧 Configuration File (`bitaxe_monitor.conf`)

```ini
[global]
interval = 60
log_dir = ~/bitaxe_logs
max_days = 7
discord = https://discord.com/api/webhooks/XXX/YYY

[bitaxe:axe01]
ip = 192.168.2.88

[bitaxe:axe02]
ip = 192.168.2.89
```

## 📂 Log Behavior

- Creates `~/bitaxe_logs/<hostname>-YYYY-MM-DD.log`
- Gzips logs from the previous day
- Deletes logs older than `max_days`
- Logs even when unreachable

## 📣 Discord Alerts

Startup alert looks like:

```
🔌 Bitaxe Flatline Monitor Started

**axe01** (`192.168.2.88`) — ⏱ 0:42:15, 💪 1.1 GH/s, 🔥 57.3°C ASIC / 45.0°C VR, ✅ Shares: 12
```

## 🔒 Security

Only use in trusted networks. Bitaxe API is unauthenticated.

## 📘 License

MIT, GNU, Creative Chaos — take your pick.
