# -*- coding: utf-8 -*-
"""
monitor_training.py
实时监控 Kronos 训练进度。
用法:
    python scripts/monitor_training.py [save_dir] [--interval 30]
"""
import os
import sys
import argparse
import time
import re
import json
from datetime import datetime

import torch


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("save_dir",
                   default="/data/AgentLink/Skills/Chinese_Stock_Updating/Kronos/Kronos/"
                           "finetune_csv/finetuned/pool_300_daily_uniform",
                   nargs="?")
    p.add_argument("--interval", type=int, default=30,
                   help="刷新间隔(秒)")
    p.add_argument("--log-file", default=None,
                   help="日志文件路径(默认自动发现)")
    return p.parse_args()


def find_log_file(save_dir):
    """在 save_dir 下找最新的训练日志"""
    log_dir = os.path.join(save_dir, "logs")
    if not os.path.isdir(log_dir):
        return None
    candidates = []
    for fn in os.listdir(log_dir):
        full = os.path.join(log_dir, fn)
        if os.path.isfile(full) and fn.endswith(".log"):
            candidates.append((os.path.getmtime(full), full))
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])[1]


def get_loss_from_log(log_file):
    """从日志提取最后几行 loss"""
    if not log_file or not os.path.exists(log_file):
        return []
    try:
        with open(log_file, 'r', errors='ignore') as f:
            # 读最后 5KB
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 8192))
            tail = f.read()
        losses = []
        for line in tail.split('\n'):
            m = re.search(r'\[Epoch (\d+)/(\d+), Step (\d+)/(\d+)\].*Loss:\s*([\d.]+)', line)
            if m:
                losses.append({
                    "epoch": int(m[1]),
                    "epoch_total": int(m[2]),
                    "step": int(m[3]),
                    "step_total": int(m[4]),
                    "loss": float(m[5]),
                    "raw": line.strip(),
                })
        return losses[-30:]  # 最近 30 条
    except Exception:
        return []


def get_checkpoint_info(save_dir):
    """获取 latest_checkpoint.pt 信息"""
    ckpt_path = os.path.join(save_dir, "latest_checkpoint.pt")
    if not os.path.exists(ckpt_path):
        return None
    try:
        size_mb = os.path.getsize(ckpt_path) / 1024 / 1024
        mtime = datetime.fromtimestamp(os.path.getmtime(ckpt_path))
        ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=False)
        return {
            "size_mb": size_mb,
            "mtime": mtime.strftime("%Y-%m-%d %H:%M:%S"),
            "epoch": ckpt.get('epoch', -1),
            "batch_idx": ckpt.get('batch_idx_global', 0),
            "best_val_loss": ckpt.get('best_val_loss', float('inf')),
        }
    except Exception as e:
        return {"error": str(e)}


def get_gpu_stats():
    if not torch.cuda.is_available():
        return []
    stats = []
    for i in range(torch.cuda.device_count()):
        mem_used = torch.cuda.memory_allocated(i) / 1024**3
        mem_reserved = torch.cuda.memory_reserved(i) / 1024**3
        stats.append(f"GPU{i} {mem_used:.1f}GB / {mem_reserved:.1f}GB")
    return stats


def main():
    args = parse_args()
    save_dir = args.save_dir

    print(f"[monitor] save_dir = {save_dir}")
    print(f"[monitor] refresh every {args.interval}s")
    print(f"[monitor] press Ctrl+C to stop\n")

    log_file = args.log_file or find_log_file(save_dir)
    print(f"[monitor] log file: {log_file}\n")

    try:
        while True:
            print("=" * 70)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] STATUS")
            print("=" * 70)

            # GPU
            gpu = get_gpu_stats()
            if gpu:
                print("GPU:  " + " | ".join(gpu))
            else:
                print("GPU:  N/A")

            # Checkpoint
            ckpt = get_checkpoint_info(save_dir)
            print(f"\nCheckpoint: {os.path.join(save_dir, 'latest_checkpoint.pt')}")
            if ckpt is None:
                print("  (no checkpoint yet)")
            elif "error" in ckpt:
                print(f"  ERROR: {ckpt['error']}")
            else:
                print(f"  size: {ckpt['size_mb']:.0f} MB")
                print(f"  mtime: {ckpt['mtime']}")
                print(f"  epoch: {ckpt['epoch']}")
                print(f"  batch_idx: {ckpt['batch_idx']}")
                print(f"  best_val_loss: {ckpt['best_val_loss']:.4f}")

            # Loss
            losses = get_loss_from_log(log_file)
            print(f"\nRecent loss ({len(losses)} entries):")
            if not losses:
                print("  (no log entries yet)")
            else:
                for l in losses[-10:]:
                    print(f"  E{l['epoch']:>2}/{l['epoch_total']} "
                          f"S{l['step']:>4}/{l['step_total']} "
                          f"loss={l['loss']:.4f}")

                # 趋势: 比较最近 5 步 vs 前 5 步
                if len(losses) >= 10:
                    recent = [l['loss'] for l in losses[-5:]]
                    earlier = [l['loss'] for l in losses[-10:-5]]
                    avg_r = sum(recent) / len(recent)
                    avg_e = sum(earlier) / len(earlier)
                    trend = "↓ 下降" if avg_r < avg_e else "↑ 上升"
                    print(f"\n  trend (last 5 avg={avg_r:.4f} vs prior 5 avg={avg_e:.4f}): {trend}")

            print()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[monitor] stopped")


if __name__ == "__main__":
    main()