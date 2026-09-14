import os
import sys
import json
import time
import pickle
import random
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.utils.data.distributed import DistributedSampler
from time import gmtime, strftime
import logging
from logging.handlers import RotatingFileHandler
import datetime
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from typing import Optional

sys.path.append('../')
from model import Kronos, KronosTokenizer, KronosPredictor
from config_loader import CustomFinetuneConfig


class CustomKlineDataset(Dataset):

    def __init__(self, data_path, data_type='train', lookback_window=90, predict_window=10,
                 clip=5.0, seed=100, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15,
                 pool_mode=False, symbol_col=None, level_weights=None):
        """
        pool_mode=False (default)
            Single-file dataset. Backwards compatible with the original behaviour.
            `data_path` is a CSV with columns [timestamps, open, high, low, close,
            volume, amount]. Each row is one bar; the dataset streams sliding
            windows of length `lookback_window + predict_window + 1`.

        pool_mode=True
            Multi-symbol pool dataset. `data_path` is a long-format CSV with an
            extra `symbol` column (configurable via `symbol_col`). The dataset
            picks ONE symbol per `__getitem__` and returns a contiguous segment
            of that symbol's bars (no cross-symbol leakage). Per-symbol
            z-score normalisation is applied so high-priced names (e.g. 茅台
            1500) don't dominate the gradient.
        """
        self.data_path = data_path
        self.data_type = data_type
        self.lookback_window = lookback_window
        self.predict_window = predict_window
        self.window = lookback_window + predict_window + 1
        self.clip = clip
        self.seed = seed
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.pool_mode = bool(pool_mode)
        self.symbol_col = symbol_col or "symbol"
        self.level_weights = level_weights or {}

        self.feature_list = ['open', 'high', 'low', 'close', 'volume', 'amount']
        self.time_feature_list = ['minute', 'hour', 'weekday', 'day', 'month']

        self.py_rng = random.Random(seed)

        self._load_and_preprocess_data()
        self._split_data_by_time()

        if self.pool_mode:
            # n_samples is the SUM over symbols of usable windows.
            # We avoid drawing more windows than each symbol can supply.
            self.n_samples = max(1, sum(self._usable_windows_for(s) for s in self.symbols))
        else:
            self.n_samples = len(self.data) - self.window + 1
        if self.n_samples <= 0:
            raise ValueError(
                f"[{self.data_type}] n_samples={self.n_samples}; not enough data "
                f"after split (window={self.window})."
            )

        print(f"[{data_type.upper()}] pool_mode={self.pool_mode}  symbols={len(self.symbols) if self.pool_mode else 1}  "
              f"available samples: {self.n_samples}")

    # ------------------------------------------------------------------
    # IO
    # ------------------------------------------------------------------
    def _load_and_preprocess_data(self):
        df = pd.read_csv(self.data_path)

        df['timestamps'] = pd.to_datetime(df['timestamps'])
        if self.pool_mode:
            if self.symbol_col not in df.columns:
                raise ValueError(
                    f"pool_mode=True but column '{self.symbol_col}' not in {list(df.columns)}"
                )
            df = df.sort_values([self.symbol_col, 'timestamps']).reset_index(drop=True)
        else:
            df = df.sort_values('timestamps').reset_index(drop=True)

        self.timestamps = df['timestamps'].copy()

        df['minute'] = df['timestamps'].dt.minute
        df['hour'] = df['timestamps'].dt.hour
        df['weekday'] = df['timestamps'].dt.weekday
        df['day'] = df['timestamps'].dt.day
        df['month'] = df['timestamps'].dt.month

        if self.pool_mode:
            # Keep the symbol column around for symbol-aware sampling.
            self._raw = df.copy()  # full long-format
            self.symbols = sorted(df[self.symbol_col].unique().tolist())
            # Per-symbol level weight (default 1.0 if not specified).
            self._symbol_weights = []
            for s in self.symbols:
                lvl = self._raw.loc[self._raw[self.symbol_col] == s, 'level'].iloc[0] \
                    if 'level' in self._raw.columns else None
                self._symbol_weights.append(self.level_weights.get(lvl, 1.0))
            total = sum(self._symbol_weights)
            self._symbol_probs = [w / total for w in self._symbol_weights]
            # Pre-compute per-symbol start-index ranges so __getitem__ is O(1).
            self._symbol_offsets = {}  # symbol -> (start_row, end_row_exclusive)
            cur = 0
            for s in self.symbols:
                n = int((self._raw[self.symbol_col] == s).sum())
                self._symbol_offsets[s] = (cur, cur + n)
                cur += n
            # The "data" attribute holds the time-feature rows in the same row
            # order as _raw; we keep them aligned so __getitem__ can slice both.
            self.data = df[self.feature_list + self.time_feature_list].copy()
        else:
            self.data = df[self.feature_list + self.time_feature_list].copy()
            self.symbols = []
            self._symbol_weights = []
            self._symbol_probs = []
            self._symbol_offsets = {}

        if self.data.isnull().any().any():
            print("Warning: Missing values found in data, performing forward fill")
            self.data = self.data.fillna(method='ffill')

        print(f"Original data time range: {self.timestamps.min()} to {self.timestamps.max()}")
        print(f"Original data total length: {len(df)} records")

    # ------------------------------------------------------------------
    # Train / val split
    # ------------------------------------------------------------------
    def _split_data_by_time(self):
        if self.pool_mode:
            # Per-symbol time split: every symbol's tail becomes val/test.
            # Keeps continuity within each symbol (no cross-symbol leakage).
            self._split_pool()
            return

        total_length = len(self.data)
        train_end = int(total_length * self.train_ratio)
        val_end = int(total_length * (self.train_ratio + self.val_ratio))

        if self.data_type == 'train':
            self.data = self.data.iloc[:train_end].copy()
            self.timestamps = self.timestamps.iloc[:train_end].copy()
            print(f"[{self.data_type.upper()}] Training set: first {train_end} time points ({self.train_ratio})")
            print(f"[{self.data_type.upper()}] Training set time range: {self.timestamps.min()} to {self.timestamps.max()}")
        elif self.data_type == 'val':
            self.data = self.data.iloc[train_end:val_end].copy()
            self.timestamps = self.timestamps.iloc[train_end:val_end].copy()
            print(f"[{self.data_type.upper()}] Validation set: time points {train_end+1} to {val_end} ({self.val_ratio})")
            print(f"[{self.data_type.upper()}] Validation set time range: {self.timestamps.min()} to {self.timestamps.max()}")
        elif self.data_type == 'test':
            self.data = self.data.iloc[val_end:].copy()
            self.timestamps = self.timestamps.iloc[val_end:].copy()
            print(f"[{self.data_type.upper()}] Test set: after time point {val_end+1}")
            print(f"[{self.data_type.upper()}] Validation set time range: {self.timestamps.min()} to {self.timestamps.max()}")

        print(f"[{self.data_type.upper()}] Data length after split: {len(self.data)} records")

    def _split_pool(self):
        """For each symbol, slice the tail (val_ratio / test_ratio) by time.

        We rebuild self.data to be the in-split rows only, and re-index
        self._symbol_offsets so __getitem__ can still slice within-symbol.
        """
        # Per-symbol: pull rows by position within this symbol's slice of _raw.
        # self._raw is sorted by [symbol, timestamps] so symbols occupy
        # contiguous row ranges.
        keep_positions = []   # positions (0..N-1) within self._raw to keep
        new_offsets = {}      # symbol -> (start_new, end_new) in rebuilt self.data
        n_kept_total = 0
        cur = 0
        for s in self.symbols:
            lo, hi = self._symbol_offsets[s]
            n = hi - lo
            if n == 0:
                continue
            train_end = int(n * self.train_ratio)
            val_end = int(n * (self.train_ratio + self.val_ratio))
            if self.data_type == 'train':
                sel_lo, sel_hi = lo, lo + train_end
            elif self.data_type == 'val':
                sel_lo, sel_hi = lo + train_end, lo + val_end
            else:
                sel_lo, sel_hi = lo + val_end, hi
            if sel_hi <= sel_lo:
                continue
            keep_positions.extend(range(sel_lo, sel_hi))
            new_offsets[s] = (cur, cur + (sel_hi - sel_lo))
            cur += (sel_hi - sel_lo)
            n_kept_total += (sel_hi - sel_lo)

        if not keep_positions:
            return

        # Slice self.data (which is also a copy of self._raw's feature cols,
        # in the same row order) and rebuild per-symbol offsets.
        self.data = self.data.iloc[keep_positions].reset_index(drop=True)
        self._symbol_offsets = new_offsets

        print(f"[{self.data_type.upper()}] pool: kept {n_kept_total} rows from {len(new_offsets)} symbols")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _usable_windows_for(self, symbol: str) -> int:
        """How many distinct sliding windows of size `self.window` does this symbol support?"""
        if symbol not in self._symbol_offsets:
            return 0
        lo, hi = self._symbol_offsets[symbol]
        n = hi - lo
        return max(0, n - self.window + 1)

    def set_epoch_seed(self, epoch):
        epoch_seed = self.seed + epoch
        self.py_rng.seed(epoch_seed)
        self.current_epoch = epoch

    def __len__(self):
        return self.n_samples

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------
    def __getitem__(self, idx):
        if self.pool_mode:
            return self._getitem_pool(idx)
        return self._getitem_single(idx)

    def _getitem_single(self, idx):
        max_start = len(self.data) - self.window
        if max_start <= 0:
            raise ValueError("Data length insufficient to create samples")
        epoch = getattr(self, 'current_epoch', 0)
        if self.data_type == 'train':
            start_idx = (idx * 9973 + (epoch + 1) * 104729) % (max_start + 1)
        else:
            start_idx = idx % (max_start + 1)
        end_idx = start_idx + self.window
        window_data = self.data.iloc[start_idx:end_idx]

        x = window_data[self.feature_list].values.astype(np.float32)
        x_stamp = window_data[self.time_feature_list].values.astype(np.float32)

        x_mean, x_std = np.mean(x, axis=0), np.std(x, axis=0)
        x = (x - x_mean) / (x_std + 1e-5)
        x = np.clip(x, -self.clip, self.clip)

        x_tensor = torch.from_numpy(x)
        x_stamp_tensor = torch.from_numpy(x_stamp)
        return x_tensor, x_stamp_tensor

    def _getitem_pool(self, idx):
        # 1) Pick a symbol according to its level-weight probability.
        #    We mix in idx so different workers don't draw the same symbol in lockstep.
        epoch = getattr(self, 'current_epoch', 0)
        if self.data_type == 'train':
            rng = random.Random(self.seed + epoch * 1000003 + idx)
        else:
            rng = random.Random(self.seed + idx)
        sym_idx = rng.choices(range(len(self.symbols)), weights=self._symbol_probs, k=1)[0]
        sym = self.symbols[sym_idx]
        lo, hi = self._symbol_offsets.get(sym, (0, 0))
        usable = hi - lo - self.window + 1
        if usable <= 0:
            # Fallback: pick the symbol with the largest usable window.
            best, best_u = None, -1
            for s in self.symbols:
                u = self._usable_windows_for(s)
                if u > best_u:
                    best, best_u = s, u
            sym = best
            lo, hi = self._symbol_offsets[sym]
            usable = best_u

        # 2) Pick a start within this symbol.
        if self.data_type == 'train':
            start_offset = (idx * 9973 + (epoch + 1) * 104729) % usable
        else:
            start_offset = idx % usable
        start_idx = lo + start_offset
        end_idx = start_idx + self.window
        window_data = self.data.iloc[start_idx:end_idx]

        x = window_data[self.feature_list].values.astype(np.float32)
        x_stamp = window_data[self.time_feature_list].values.astype(np.float32)

        # 3) Per-symbol z-score (CRITICAL fix vs. the original implementation).
        x_mean, x_std = np.mean(x, axis=0), np.std(x, axis=0)
        x = (x - x_mean) / (x_std + 1e-5)
        x = np.clip(x, -self.clip, self.clip)

        x_tensor = torch.from_numpy(x)
        x_stamp_tensor = torch.from_numpy(x_stamp)
        return x_tensor, x_stamp_tensor




def setup_logging(exp_name: str, log_dir: str, rank: int = 0) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger(f"basemodel_training_rank_{rank}")
    logger.setLevel(logging.INFO)
    
    if logger.handlers:
        return logger
    
    log_file = os.path.join(log_dir, f"basemodel_training_rank_{rank}.log")
    file_handler = RotatingFileHandler(
        log_file, 
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    
    console_handler = None
    if rank == 0:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    if console_handler is not None:
        console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    if console_handler is not None:
        logger.addHandler(console_handler)
    
    logger.info(f"=== Basemodel Training Started ===")
    logger.info(f"Experiment Name: {exp_name}")
    logger.info(f"Log Directory: {log_dir}")
    logger.info(f"Rank: {rank}")
    logger.info(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return logger


def create_dataloaders(config):
    if not dist.is_available() or not dist.is_initialized() or dist.get_rank() == 0:
        print("Creating data loaders...")

    pool_kwargs = dict(
        pool_mode=getattr(config, 'pool_mode', False),
        symbol_col=getattr(config, 'symbol_col', 'symbol'),
        level_weights=getattr(config, 'level_weights', {}),
    )

    train_dataset = CustomKlineDataset(
        data_path=config.data_path,
        data_type='train',
        lookback_window=config.lookback_window,
        predict_window=config.predict_window,
        clip=config.clip,
        seed=config.seed,
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
        test_ratio=config.test_ratio,
        **pool_kwargs,
    )

    val_dataset = CustomKlineDataset(
        data_path=config.data_path,
        data_type='val',
        lookback_window=config.lookback_window,
        predict_window=config.predict_window,
        clip=config.clip,
        seed=config.seed + 1,
        train_ratio=config.train_ratio,
        val_ratio=config.val_ratio,
        test_ratio=config.test_ratio,
        **pool_kwargs,
    )
    
    use_ddp = dist.is_available() and dist.is_initialized()
    train_sampler = DistributedSampler(train_dataset, num_replicas=dist.get_world_size(), rank=dist.get_rank(), shuffle=True) if use_ddp else None
    val_sampler = DistributedSampler(val_dataset, num_replicas=dist.get_world_size(), rank=dist.get_rank(), shuffle=False, drop_last=False) if use_ddp else None

    train_loader = DataLoader(
        train_dataset,
        batch_size=config.batch_size,
        shuffle=(train_sampler is None),
        num_workers=config.num_workers,
        pin_memory=True,
        drop_last=True,
        sampler=train_sampler
    )
    
    val_loader = DataLoader(
        val_dataset,
        batch_size=config.batch_size,
        shuffle=False,
        num_workers=config.num_workers,
        pin_memory=True,
        drop_last=False,
        sampler=val_sampler
    )
    
    if not dist.is_available() or not dist.is_initialized() or dist.get_rank() == 0:
        print(f"Training set size: {len(train_dataset)}, Validation set size: {len(val_dataset)}")
    
    return train_loader, val_loader, train_dataset, val_dataset, train_sampler, val_sampler


def train_model(model, tokenizer, device, config, save_dir, logger, resume_from: Optional[str] = None):
    logger.info("Starting training...")
    use_ddp = dist.is_available() and dist.is_initialized()
    rank = dist.get_rank() if use_ddp else 0
    world_size = dist.get_world_size() if use_ddp else 1

    train_loader, val_loader, train_dataset, val_dataset, train_sampler, val_sampler = create_dataloaders(config)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.predictor_learning_rate,
        betas=(config.adam_beta1, config.adam_beta2),
        weight_decay=config.adam_weight_decay
    )

    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=config.predictor_learning_rate,
        steps_per_epoch=len(train_loader),
        epochs=config.basemodel_epochs,
        pct_start=0.03,
        div_factor=10
    )

    if use_ddp:
        local_rank = int(os.environ.get("LOCAL_RANK", "0"))
        model = DDP(model, device_ids=[local_rank], output_device=local_rank, find_unused_parameters=False)

    best_val_loss = float('inf')
    batch_idx_global = 0
    start_epoch = 0

    # ---------- 断点训练恢复 ----------
    ckpt = None
    if resume_from is None and os.path.isdir(save_dir):
        auto_ckpt = os.path.join(save_dir, "latest_checkpoint.pt")
        if os.path.exists(auto_ckpt):
            resume_from = auto_ckpt
            logger.info(f"Auto-resume detected: {resume_from}")
    if resume_from and os.path.exists(resume_from):
        ckpt = torch.load(resume_from, map_location='cpu', weights_only=False)
        raw = model.module if use_ddp else model
        raw.load_state_dict(ckpt['model_state_dict'])
        try:
            optimizer.load_state_dict(ckpt['optimizer_state_dict'])
        except Exception as e:
            logger.warning(f"[RESUME] optimizer state 不兼容,跳过 (常见于 config 变更): {e}")
        try:
            scheduler.load_state_dict(ckpt['scheduler_state_dict'])
            if 'last_epoch' in ckpt:
                scheduler.last_epoch = ckpt['last_epoch']
        except Exception as e:
            logger.warning(f"[RESUME] scheduler state 不兼容,跳过: {e}")
        start_epoch = ckpt['epoch'] + 1
        batch_idx_global = ckpt.get('batch_idx_global', 0)
        best_val_loss = ckpt.get('best_val_loss', float('inf'))
        if 'rng_state' in ckpt:
            torch.manual_seed(ckpt['rng_state'])
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(ckpt['rng_state'])
            logger.info(f"Restored RNG state")
        logger.info(f"[RESUME] basemodel from epoch {start_epoch}/{config.basemodel_epochs}, "
                    f"best_val_loss={best_val_loss:.4f}")
        if rank == 0:
            print(f"\n[RESUME] basemodel from epoch {start_epoch}/{config.basemodel_epochs}")
    # ----------------------------------

    for epoch in range(start_epoch, config.basemodel_epochs):
        epoch_start_time = time.time()
        model.train()

        train_dataset.set_epoch_seed(epoch * 10000)
        val_dataset.set_epoch_seed(0)
        if train_sampler is not None:
            train_sampler.set_epoch(epoch)
        
        epoch_train_loss = 0.0
        train_batches = 0
        
        for batch_idx, (batch_x, batch_x_stamp) in enumerate(train_loader):
            batch_x = batch_x.to(device, non_blocking=True)
            batch_x_stamp = batch_x_stamp.to(device, non_blocking=True)
            
            with torch.no_grad():
                token_seq_0, token_seq_1 = tokenizer.encode(batch_x, half=True)

            token_in = [token_seq_0[:, :-1], token_seq_1[:, :-1]]
            token_out = [token_seq_0[:, 1:], token_seq_1[:, 1:]]

            logits = (model.module if use_ddp else model)(token_in[0], token_in[1], batch_x_stamp[:, :-1, :])
            ce_loss, s1_loss, s2_loss = (model.module if use_ddp else model).head.compute_loss(logits[0], logits[1], token_out[0], token_out[1])

            # ------------------------------------------------------------------
            # Direction loss (optional): align the sign of token-id changes over
            # the LAST `pred_len` steps between predicted argmax and ground truth.
            #
            # The intuition: if the model predicts an upward token transition and
            # the ground truth is also an upward transition, this term goes to 0;
            # otherwise to -2. We minimise the negative of this so that aligned
            # pairs pull the loss towards 0.
            #
            # This is a cheap proxy for "predicted direction == realised direction"
            # without having to decode back to close values.
            # ------------------------------------------------------------------
            dir_loss = torch.zeros((), device=device)
            dir_weight = float(getattr(config, "dir_loss_weight", 0.0))
            if dir_weight > 0.0 and config.predict_window > 1:
                with torch.no_grad():
                    pred_s1 = logits[0].argmax(dim=-1)        # (B, T)
                T = pred_s1.size(1)
                pl = config.predict_window
                if T > pl:
                    pred_diff = pred_s1[:, -pl:] - pred_s1[:, -pl - 1:-1]
                    true_diff = token_out[0][:, -pl:] - token_out[0][:, -pl - 1:-1]
                    align = torch.sign((pred_diff * true_diff).float())
                    # Convert -1/+1 to 0/1 and take mean (matches DA definition).
                    dir_loss = -align.mean()
            loss = ce_loss + dir_weight * dir_loss

            # ------------------------------------------------------------------
            # Ranking loss (optional, target=筛选器):
            # 让 Kronos 学"5 日相对排名"而非"绝对方向"。
            # ground truth: 每个样本的最后 predict_window 个 token 之差 → 真实 5 日涨跌
            # prediction:   模型 argmax 序列的对应 token 之差
            # loss: ListMLE,让预测排名与真实排名一致(排序学习)
            #
            # 这是 1 epoch 模型对反指过滤器不够准的根因 — 学"绝对方向"
            # 比学"相对排序"难得多。加入这个 loss 让 Kronos 直接对齐"哪只最差"。
            # ------------------------------------------------------------------
            rank_loss = torch.zeros((), device=device)
            rank_weight = float(getattr(config, "rank_loss_weight", 0.0))
            if rank_weight > 0.0:
                with torch.no_grad():
                    pred_s1 = logits[0].argmax(dim=-1)        # (B, T)
                    true_s1 = token_out[0]                    # (B, T)
                T = pred_s1.size(1)
                pl = config.predict_window
                if batch_idx_global < 3:
                    print(f"  [debug] T={T}, pl={pl}, rank_weight={rank_weight}, B={batch_x.shape[0]}")
                if T > pl:
                    pred_score = (pred_s1[:, -pl:].float() -
                                  pred_s1[:, -pl - 1:-1].float()).sum(dim=-1)  # (B,)
                    true_score = (true_s1[:, -pl:].float() -
                                  true_s1[:, -pl - 1:-1].float()).sum(dim=-1)  # (B,)
                    B = pred_score.size(0)
                    if batch_idx_global < 3:
                        print(f"  [debug] pred_score[:4]={pred_score[:4].tolist()}, "
                              f"true_score[:4]={true_score[:4].tolist()}")
                    if B >= 2:
                        # Pairwise margin ranking loss (修复版):
                        # 对每对 (i, j),如果 true_i > true_j,则要 pred_i > pred_j,
                        # 用 hinge-style loss: max(0, margin - (pred_i - pred_j))
                        diff_pred = pred_score.unsqueeze(1) - pred_score.unsqueeze(0)  # (B, B)
                        diff_true = true_score.unsqueeze(1) - true_score.unsqueeze(0)  # (B, B)
                        # mask: 只保留 true_i > true_j (避免对称重复)
                        margin = 0.5
                        pair_loss = torch.clamp(margin - diff_pred, min=0.0)
                        # 只对 true_diff > 0 的对算 loss
                        pair_loss = pair_loss * (diff_true > 0).float()
                        # 屏蔽 i==j
                        eye_mask = 1.0 - torch.eye(B, device=device)
                        pair_loss = pair_loss * eye_mask
                        # 归一化:除以有效对数
                        n_pairs = (diff_true > 0).float().sum() + 1e-6
                        rank_loss = pair_loss.sum() / n_pairs
            loss = loss + rank_weight * rank_loss
            
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_((model.module if use_ddp else model).parameters(), max_norm=3.0)
            optimizer.step()
            scheduler.step()
            
            epoch_train_loss += loss.item()
            train_batches += 1
            
            if (batch_idx_global + 1) % config.log_interval == 0:
                lr = optimizer.param_groups[0]['lr']
                log_msg = (f"[Epoch {epoch+1}/{config.basemodel_epochs}, Step {batch_idx+1}/{len(train_loader)}] "
                          f"LR: {lr:.6f}, Loss: {loss.item():.4f} "
                          f"(ce={ce_loss.item():.4f} dir={dir_loss.item():+.4f} "
                          f"rank={rank_loss.item():+.6f})")
                logger.info(log_msg)
                if rank == 0:
                    print(log_msg)
            
            batch_idx_global += 1
        
        model.eval()
        val_loss = 0.0
        val_batches = 0
        
        with torch.no_grad():
            for batch_x, batch_x_stamp in val_loader:
                batch_x = batch_x.to(device, non_blocking=True)
                batch_x_stamp = batch_x_stamp.to(device, non_blocking=True)
                
                token_seq_0, token_seq_1 = tokenizer.encode(batch_x, half=True)
                token_in = [token_seq_0[:, :-1], token_seq_1[:, :-1]]
                token_out = [token_seq_0[:, 1:], token_seq_1[:, 1:]]
                
                logits = (model.module if use_ddp else model)(token_in[0], token_in[1], batch_x_stamp[:, :-1, :])
                loss, _, _ = (model.module if use_ddp else model).head.compute_loss(logits[0], logits[1], token_out[0], token_out[1])
                
                val_loss += loss.item()
                val_batches += 1
        
        if use_ddp:
            tensor_sum = torch.tensor([epoch_train_loss, train_batches, val_loss, val_batches], dtype=torch.float64, device=device)
            dist.all_reduce(tensor_sum, op=dist.ReduceOp.SUM)
            epoch_train_loss_all = tensor_sum[0].item()
            train_batches_all = int(tensor_sum[1].item())
            val_loss_all = tensor_sum[2].item()
            val_batches_all = int(tensor_sum[3].item())
            avg_train_loss = (epoch_train_loss_all / train_batches_all) if train_batches_all > 0 else 0.0
            avg_val_loss = (val_loss_all / val_batches_all) if val_batches_all > 0 else 0.0
        else:
            avg_train_loss = epoch_train_loss / train_batches if train_batches > 0 else 0
            avg_val_loss = val_loss / val_batches if val_batches > 0 else 0
        
        epoch_time = time.time() - epoch_start_time
        epoch_summary = (f"\n--- Epoch {epoch+1}/{config.basemodel_epochs} Summary ---\n"
                       f"Training Loss: {avg_train_loss:.4f}\n"
                       f"Validation Loss: {avg_val_loss:.4f}\n"
                       f"Epoch Time: {epoch_time:.2f} seconds\n")
        logger.info(epoch_summary)
        if rank == 0:
            print(epoch_summary)
        
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            if rank == 0:
                model_save_path = os.path.join(save_dir, "best_model")
                os.makedirs(model_save_path, exist_ok=True)
                (model.module if use_ddp else model).save_pretrained(model_save_path)
                save_msg = f"Best model saved to: {model_save_path} (validation loss: {best_val_loss:.4f})"
                logger.info(save_msg)
                print(save_msg)

        # ---------- 每 epoch 结束保存 checkpoint (供断点恢复) ----------
        if rank == 0:
            ckpt_path = os.path.join(save_dir, "latest_checkpoint.pt")
            raw = model.module if use_ddp else model
            torch.save({
                'epoch': epoch,
                'batch_idx_global': batch_idx_global,
                'model_state_dict': raw.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'scheduler_state_dict': scheduler.state_dict(),
                'last_epoch': getattr(scheduler, 'last_epoch', epoch),
                'best_val_loss': best_val_loss,
                'rng_state': torch.get_rng_state(),
            }, ckpt_path)
            logger.info(f"Checkpoint saved: {ckpt_path}")
        # --------------------------------------------------------

    return best_val_loss


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Kronos Basemodel Fine-tuning Training')
    parser.add_argument('--config', type=str, default='config.yaml', 
                       help='Configuration file path (default: config.yaml)')
    args = parser.parse_args()
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    config = CustomFinetuneConfig(args.config)
    
    os.makedirs(config.basemodel_save_path, exist_ok=True)
    
    log_dir = os.path.join(config.base_save_path, "logs")
    logger = setup_logging(config.exp_name, log_dir, 0)
    
    torch.manual_seed(config.seed)
    np.random.seed(config.seed)
    random.seed(config.seed)
    
    logger.info("Loading pretrained model or random initialization...")
    print("Loading pretrained model or random initialization...")
    if getattr(config, 'pre_trained_tokenizer', True):
        tokenizer = KronosTokenizer.from_pretrained(config.finetuned_tokenizer_path)
    else:
        import json, os
        print("pre_trained_tokenizer=False, randomly initializing Tokenizer architecture for training")
        cfg_path_tok = os.path.join(config.pretrained_tokenizer_path if hasattr(config, 'pretrained_tokenizer_path') else config.finetuned_tokenizer_path, 'config.json')
        with open(cfg_path_tok, 'r') as f:
            arch_t = json.load(f)
        tokenizer = KronosTokenizer(
            d_in=arch_t.get('d_in', 6),
            d_model=arch_t.get('d_model', 256),
            n_heads=arch_t.get('n_heads', 4),
            ff_dim=arch_t.get('ff_dim', 512),
            n_enc_layers=arch_t.get('n_enc_layers', 4),
            n_dec_layers=arch_t.get('n_dec_layers', 4),
            ffn_dropout_p=arch_t.get('ffn_dropout_p', 0.0),
            attn_dropout_p=arch_t.get('attn_dropout_p', 0.0),
            resid_dropout_p=arch_t.get('resid_dropout_p', 0.0),
            s1_bits=arch_t.get('s1_bits', 10),
            s2_bits=arch_t.get('s2_bits', 10),
            beta=arch_t.get('beta', 0.05),
            gamma0=arch_t.get('gamma0', 1.0),
            gamma=arch_t.get('gamma', 1.1),
            zeta=arch_t.get('zeta', 0.05),
            group_size=arch_t.get('group_size', 4)
        )

    if getattr(config, 'pre_trained_predictor', True):
        model = Kronos.from_pretrained(config.pretrained_predictor_path)
    else:
        import json, os
        print("pre_trained_predictor=False, randomly initializing Predictor architecture for training")
        cfg_path = os.path.join(config.pretrained_predictor_path, 'config.json')
        with open(cfg_path, 'r') as f:
            arch = json.load(f)
        model = Kronos(
            s1_bits=arch.get('s1_bits', 10),
            s2_bits=arch.get('s2_bits', 10),
            n_layers=arch.get('n_layers', 12),
            d_model=arch.get('d_model', 832),
            n_heads=arch.get('n_heads', 16),
            ff_dim=arch.get('ff_dim', 2048),
            ffn_dropout_p=arch.get('ffn_dropout_p', 0.2),
            attn_dropout_p=arch.get('attn_dropout_p', 0.0),
            resid_dropout_p=arch.get('resid_dropout_p', 0.2),
            token_dropout_p=arch.get('token_dropout_p', 0.0),
            learn_te=arch.get('learn_te', True)
        )
    
    tokenizer = tokenizer.to(device)
    model = model.to(device)
    
    model_size = sum(p.numel() for p in model.parameters())
    logger.info(f"Model parameters: {model_size:,}")
    print(f"Model parameters: {model_size:,}")
    
    logger.info("=== Training Configuration ===")
    logger.info(f"Data path: {config.data_path}")
    logger.info(f"Lookback window: {config.lookback_window}")
    logger.info(f"Predict window: {config.predict_window}")
    logger.info(f"Batch size: {config.batch_size}")
    logger.info(f"Learning rate: {config.predictor_learning_rate}")
    logger.info(f"Training epochs: {config.basemodel_epochs}")
    logger.info(f"Device: {device}")
    logger.info(f"Tokenizer path: {config.finetuned_tokenizer_path}")
    logger.info(f"Pretrained model path: {config.pretrained_predictor_path}")
    
    logger.info("Starting fine-tuning training...")
    print("Starting fine-tuning training...")
    best_val_loss = train_model(model, tokenizer, device, config, config.basemodel_save_path, logger)
    
    final_msg = f"Training completed! Best validation loss: {best_val_loss:.4f}\nModel saved to: {config.basemodel_save_path}"
    logger.info(final_msg)
    print(final_msg)


if __name__ == "__main__":
    main()
