#!/usr/bin/env python3

# Bitaxe Flatline Monitor v0.13
# - Config mode w/ multiple miners
# - Immediate log creation (even on error)
# - Discord alerts (startup, restart, unreachable)
# - Log rotation, gzip, cleanup by age

import time
import requests
import argparse
from datetime import datetime, timedelta
import sys
import math
import os
import re
import gzip
import glob
import configparser
import threading

# ANSI Colors
COLOR_TIMESTAMP = "\033[92m"
COLOR_HOSTNAME = "\033[96m"
COLOR_UPTIME = "\033[38;5;36m"
COLOR_HASHRATE = "\033[94m"
COLOR_ASIC_TEMP = "\033[91m"
COLOR_VR_TEMP = "\033[95m"
COLOR_SHARES = "\033[93m"
COLOR_RESTARTS = "\033[96m"
COLOR_COUNTDOWN = "\033[96m"
COLOR_RESET = "\033[0m"

ansi_escape = re.compile(r'\x1b\[[0-9;]*m')

def countdown_timer(seconds):
    for remaining in range(seconds, 0, -1):
        sys.stdout.write(f"\rNext check in: {COLOR_COUNTDOWN}{remaining:2d} seconds{COLOR_RESET} ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r" + " " * 40 + "\r")

def format_uptime(uptime_seconds):
    try:
        uptime_td = timedelta(seconds=int(uptime_seconds))
        return str(uptime_td)
    except Exception:
        return "N/A"

def resolve_logfile(log_arg, ip, hostname=None):
    if not log_arg:
        return None
    log_arg = os.path.expanduser(log_arg)
    today = datetime.now().strftime("%Y-%m-%d")

    if os.path.isdir(log_arg) or log_arg.endswith('/'):
        os.makedirs(log_arg, exist_ok=True)
        log_name = f"{hostname or 'unknown-' + ip.replace('.', '_')}-{today}.log"
        return os.path.join(log_arg, log_name)
    else:
        os.makedirs(os.path.dirname(log_arg), exist_ok=True)
        return log_arg

def log_output(line, logfile=None):
    print(line)
    if logfile:
        plain_line = ansi_escape.sub('', line)
        with open(logfile, "a") as f:
            f.write(plain_line + "\n")

def compress_yesterdays_log(log_dir, hostname_or_ip):
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    pattern = os.path.join(log_dir, f"{hostname_or_ip}-{yesterday}.log")
    if os.path.isfile(pattern):
        gz_path = pattern + ".gz"
        if not os.path.exists(gz_path):
            with open(pattern, 'rb') as f_in:
                with gzip.open(gz_path, 'wb') as f_out:
                    f_out.writelines(f_in)
            os.remove(pattern)

def delete_old_logs(log_dir, hostname_or_ip, max_days):
    cutoff = datetime.now() - timedelta(days=max_days)
    for log_file in glob.glob(os.path.join(log_dir, f"{hostname_or_ip}-*.log*")):
        basename = os.path.basename(log_file)
        date_part = basename.split("-")[-1].split(".")[0]
        try:
            file_date = datetime.strptime(date_part, "%Y-%m-%d")
            if file_date < cutoff:
                os.remove(log_file)
        except ValueError:
            continue

def send_discord_alert(webhook_url, message):
    try:
        requests.post(webhook_url, json={"content": message}, timeout=5)
    except Exception as e:
        print(f"⚠️ Discord alert failed: {e}")

def get_bitaxe_summary(ip):
    try:
        response = requests.get(f"http://{ip}/api/system/info", timeout=5)
        response.raise_for_status()
        data = response.json()

        hostname = data.get("hostname", ip)
        hashrate = data.get("hashRate", 0)
        shares = data.get("sharesAccepted", 0)
        asic_temp = data.get("temp", "N/A")
        vr_temp = data.get("vrTemp", "N/A")
        uptime = data.get("uptimeSeconds", 0)
        uptime_td = str(timedelta(seconds=int(uptime))) if uptime else "N/A"

        return f"**{hostname}** (`{ip}`) — ⏱ {uptime_td}, 💪 {round(hashrate,1)} GH/s, 🔥 {asic_temp}°C ASIC / {vr_temp}°C VR, ✅ Shares: {shares}"
    except Exception as e:
        return f"**{ip}** — ⚠️ Error fetching stats: `{e}`"

def monitor_bitaxe(ip: str, interval: int = 60, log_arg: str = None, max_days: int = None, discord_url: str = None):
    prev_shares = None
    restart_count = 0
    stats_url = f"http://{ip}/api/system/info"
    restart_url = f"http://{ip}/api/system/restart"
    host_for_logs = ip.replace('.', '_')

    # Init log immediately
    logfile = resolve_logfile(log_arg, ip, host_for_logs) if log_arg else None
    log_dir = os.path.dirname(logfile) if logfile else None

    if log_dir and os.path.isdir(log_dir):
        compress_yesterdays_log(log_dir, host_for_logs)
        if max_days:
            delete_old_logs(log_dir, host_for_logs, max_days)

    while True:
        wait_after_restart = False
        try:
            response = requests.get(stats_url, timeout=5)
            response.raise_for_status()
            data = response.json()

            hostname = data.get("hostname", "N/A")
            host_for_logs = hostname if hostname != "N/A" else host_for_logs

            # Rename log with actual hostname if needed
            if log_arg and logfile and "unknown" in logfile:
                logfile = resolve_logfile(log_arg, ip, host_for_logs)

            hashrate = data.get("hashRate", "N/A")
            if isinstance(hashrate, (int, float)):
                hashrate = math.ceil(hashrate * 10) / 10
            else:
                hashrate = "N/A"

            asic_temp = data.get("temp", "N/A")
            if isinstance(asic_temp, (int, float)):
                asic_temp = round(asic_temp, 1)

            vr_temp = data.get("vrTemp", "N/A")
            shares = data.get("sharesAccepted", 0)
            uptime_seconds = data.get("uptimeSeconds", None)
            uptime_str = format_uptime(uptime_seconds)

            now = datetime.now().strftime("%d %b %Y %H:%M:%S")
            output = (f"{COLOR_TIMESTAMP}[{now}]{COLOR_RESET} "
                      f"Host: {COLOR_HOSTNAME}{hostname}{COLOR_RESET} | "
                      f"Uptime: {COLOR_UPTIME}{uptime_str}{COLOR_RESET} | "
                      f"Hash: {COLOR_HASHRATE}{hashrate} GH/s{COLOR_RESET} | "
                      f"ASIC: {COLOR_ASIC_TEMP}{asic_temp}°C{COLOR_RESET} | "
                      f"VR: {COLOR_VR_TEMP}{vr_temp}°C{COLOR_RESET} | "
                      f"Shares: {COLOR_SHARES}{shares}{COLOR_RESET} | "
                      f"Restarts: {COLOR_RESTARTS}{restart_count}{COLOR_RESET}")
            log_output(output, logfile)

            if prev_shares is not None:
                if shares == prev_shares:
                    log_output("❗ No new shares detected. Restarting Bitaxe...", logfile)
                    if discord_url:
                        send_discord_alert(discord_url, f"❗ Bitaxe at `{ip}` had no new shares. Restarting...")
                    try:
                        restart_resp = requests.post(restart_url, timeout=5)
                        if restart_resp.status_code == 200:
                            restart_count += 1
                            log_output("✅ Restart command sent successfully.", logfile)
                            if discord_url:
                                send_discord_alert(discord_url, f"✅ Bitaxe at `{ip}` restarted successfully.")
                        else:
                            log_output(f"⚠️ Failed to restart Bitaxe: {restart_resp.status_code}", logfile)
                            if discord_url:
                                send_discord_alert(discord_url, f"⚠️ Bitaxe at `{ip}` failed to restart: {restart_resp.status_code}")
                    except requests.RequestException as e:
                        log_output(f"🚫 Error sending restart command: {e}", logfile)
                        if discord_url:
                            send_discord_alert(discord_url, f"🚫 Error restarting Bitaxe at `{ip}`: {e}")
            else:
                log_output("⏳ Initial share count received. Monitoring for changes...", logfile)

            prev_shares = shares

        except requests.RequestException as e:
            log_output(f"🚫 Error communicating with Bitaxe at {ip}: {e}", logfile)
            if discord_url:
                send_discord_alert(discord_url, f"🚫 Could not communicate with Bitaxe at `{ip}`: {e}")
            countdown_timer(10)
            continue

        countdown_timer(60 if wait_after_restart else interval)

def run_from_config(config_file):
    config = configparser.ConfigParser()
    config.read(config_file)

    global_opts = config["global"]
    interval = int(global_opts.get("interval", 60))
    log_dir = os.path.expanduser(global_opts.get("log_dir", "./logs"))
    max_days = int(global_opts.get("max_days", 7))
    discord = global_opts.get("discord", None)

    summaries = []
    for section in config.sections():
        if section.startswith("bitaxe:"):
            ip = config[section].get("ip")
            if ip:
                summaries.append(get_bitaxe_summary(ip))

    if discord:
        startup_msg = "**🔌 Bitaxe Flatline Monitor Started**\n\n" + "\n".join(summaries)
        send_discord_alert(discord, startup_msg)

    for section in config.sections():
        if section.startswith("bitaxe:"):
            ip = config[section].get("ip")
            if ip:
                threading.Thread(
                    target=monitor_bitaxe,
                    args=(ip, interval, log_dir, max_days, discord),
                    daemon=True
                ).start()

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 Bitaxe monitoring stopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bitaxe Flatline Monitor v0.13")
    parser.add_argument("ip", nargs="?", help="Bitaxe IP (single CLI mode)")
    parser.add_argument("-i", "-interval", type=int, default=60, help="Interval in seconds")
    parser.add_argument("-l", "-log", metavar="PATH", help="Log file or directory")
    parser.add_argument("-m", "-max-days", type=int, help="Delete logs older than N days")
    parser.add_argument("-d", "-discord", metavar="URL", help="Discord webhook URL for alerts")
    parser.add_argument("-c", "-config", metavar="FILE", help="Path to config file")
    args = parser.parse_args()

    if args.c:
        run_from_config(args.c)
    elif args.ip:
        monitor_bitaxe(args.ip, args.i, args.l, args.m, args.d)
    else:
        print("💥 Error: Provide either -c <configfile> or an IP address.")
