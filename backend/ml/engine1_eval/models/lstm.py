"""A single global LSTM trained across many series (D-05, "global LSTM").

One network forecasts every series of a kind: each input window is divided by its own mean, so the
network learns shapes (relative level, persistence, bursts) rather than any one student's amounts,
and the output is multiplied back. Training uses an L1 loss, which matches MASE.

Leakage controls (the reason `until` exists): training windows must END before `until`, and the
evaluation harness only tests from `until` onwards. The synthetic profiles share one calendar, so
a model trained on other profiles' exam weeks would otherwise be tested on those same weeks.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import numpy as np
import torch
from torch import nn

from ml.engine1_eval.data import DAYS_PER_WEEK, Series

EPS = 1e-9


@dataclass(frozen=True)
class LstmConfig:
    window: int = 26
    horizon: int = 13
    hidden: int = 32
    epochs: int = 20
    batch_size: int = 256
    learning_rate: float = 1e-3
    window_stride: int = 2
    patience: int = 3
    validation_share: float = 0.1
    seed: int = 0


class _Network(nn.Module):
    def __init__(self, hidden: int, horizon: int) -> None:
        super().__init__()
        self.lstm = nn.LSTM(1, hidden, batch_first=True)
        self.head = nn.Linear(hidden, horizon)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :])


def _context(history: np.ndarray, window: int) -> np.ndarray:
    """The last `window` weeks, left-padded with the history's mean when it is shorter."""
    tail = np.asarray(history[-window:], dtype=float)
    if len(tail) < window:
        tail = np.concatenate([np.full(window - len(tail), tail.mean()), tail])
    return tail


def build_windows(
    series: Iterable[Series], config: LstmConfig, until: date | None
) -> tuple[np.ndarray, np.ndarray]:
    """Scaled (context, target) pairs whose target ends strictly before `until`."""
    xs, ys = [], []
    for s in series:
        limit = len(s)
        if until is not None:
            days = (until - s.start).days
            limit = min(limit, max(0, -(-days // DAYS_PER_WEEK)))  # weeks strictly before `until`
        for end in range(config.window, limit - config.horizon + 1, config.window_stride):
            context = s.values[end - config.window : end]
            mean = context.mean()
            if mean <= EPS:
                continue
            xs.append(context / mean)
            ys.append(s.values[end : end + config.horizon] / mean)
    if not xs:
        return np.empty((0, config.window)), np.empty((0, config.horizon))
    return np.array(xs, dtype=np.float32), np.array(ys, dtype=np.float32)


class GlobalLstm:
    name = "lstm"

    def __init__(self, network: _Network, config: LstmConfig) -> None:
        self._network = network.eval()
        self.config = config

    @property
    def parameter_count(self) -> int:
        return sum(p.numel() for p in self._network.parameters())

    def state(self) -> dict[str, torch.Tensor]:
        return {k: v.clone() for k, v in self._network.state_dict().items()}

    @classmethod
    def train(
        cls, series: Iterable[Series], config: LstmConfig, until: date | None = None
    ) -> "GlobalLstm":
        series = list(series)
        torch.manual_seed(config.seed)
        generator = np.random.default_rng(config.seed)
        split = max(1, int(len(series) * (1 - config.validation_share)))
        train_x, train_y = build_windows(series[:split], config, until)
        valid_x, valid_y = build_windows(series[split:], config, until)
        if len(train_x) == 0:
            raise ValueError("no training windows: the series are too short or end after `until`")

        network = _Network(config.hidden, config.horizon)
        optimiser = torch.optim.Adam(network.parameters(), lr=config.learning_rate)
        loss_fn = nn.L1Loss()
        best, best_state, stale = float("inf"), None, 0
        for _ in range(config.epochs):
            network.train()
            order = generator.permutation(len(train_x))
            for begin in range(0, len(order), config.batch_size):
                pick = order[begin : begin + config.batch_size]
                x = torch.from_numpy(train_x[pick]).unsqueeze(-1)
                y = torch.from_numpy(train_y[pick])
                optimiser.zero_grad()
                loss_fn(network(x), y).backward()
                optimiser.step()
            if not len(valid_x):
                continue  # nothing to validate on: train every epoch rather than stop at once
            network.eval()
            with torch.no_grad():
                x = torch.from_numpy(valid_x).unsqueeze(-1)
                score = float(loss_fn(network(x), torch.from_numpy(valid_y)))
            if score < best - 1e-6:
                best, stale = score, 0
                best_state = {k: v.clone() for k, v in network.state_dict().items()}
            else:
                stale += 1
                if stale >= config.patience:
                    break
        if best_state is not None:
            network.load_state_dict(best_state)
        return cls(network, config)

    def forecast(self, history: np.ndarray, horizon: int, start: date) -> np.ndarray:
        if horizon > self.config.horizon:
            raise ValueError(f"trained for {self.config.horizon} weeks, asked for {horizon}")
        context = _context(history, self.config.window)
        mean = float(context.mean())
        if mean <= EPS:
            return np.zeros(horizon)
        x = torch.from_numpy((context / mean).astype(np.float32)).reshape(1, -1, 1)
        with torch.no_grad():
            ratio = self._network(x)[0].numpy()[:horizon]
        return np.clip(ratio.astype(float) * mean, 0.0, None)
