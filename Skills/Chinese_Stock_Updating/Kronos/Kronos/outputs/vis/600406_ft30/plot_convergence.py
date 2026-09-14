import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

df = pd.read_csv("outputs/vis/600406_ft30/basemodel_convergence.csv")
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(df.epoch, df.train, "o-", color="tab:blue", label="train loss")
ax.plot(df.epoch, df.val, "s-", color="tab:orange", label="val loss")
ax.axvline(df.val.idxmin() + 1, color="grey", linestyle="--", lw=1,
           label=f"best val @ epoch {df.val.idxmin()+1}")
ax.set_xlabel("epoch")
ax.set_ylabel("loss")
ax.set_title("Basemodel fine-tune convergence  —  600406 daily, lookback=200, predict=5\n"
             f"best val = {df.val.min():.4f}  ·  final train-val gap = {df.train.iloc[-1]-df.val.iloc[-1]:+.3f}")
ax.legend()
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig("outputs/vis/600406_ft30/00_convergence.png", dpi=120, bbox_inches="tight")
print("saved outputs/vis/600406_ft30/00_convergence.png")