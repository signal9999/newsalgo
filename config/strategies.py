"""
マルチ戦略設定

4つの戦略を同時に走らせ、独立したペーパートレードで比較する。
LLM分析は1回だけ実行し、全戦略で使い回す（コスト最適化）。
"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class StrategyConfig:
    id: str                                  # "A" / "B" / "C" / "D"
    name: str                                # 表示名
    min_score: float = 0.5                   # このスコア以上でエントリー
    require_symbols: bool = False            # Trueなら affected_symbols が必須
    allowed_sources: Optional[List[str]] = None  # None=全ソース / ["tdnet"] など
    contrarian: bool = False                 # True=シグナルと逆方向にエントリー
    initial_balance: float = 1_000_000.0     # 初期残高（各戦略独立）


STRATEGIES: List[StrategyConfig] = [
    StrategyConfig(
        id="A",
        name="速報反応型",
        min_score=0.5,
        require_symbols=False,
        allowed_sources=None,
        contrarian=False,
    ),
    StrategyConfig(
        id="B",
        name="精度重視型",
        min_score=0.6,
        require_symbols=True,
        allowed_sources=None,
        contrarian=False,
    ),
    StrategyConfig(
        id="C",
        name="TDnetのみ",
        min_score=0.5,
        require_symbols=True,
        allowed_sources=["tdnet"],
        contrarian=False,
    ),
    StrategyConfig(
        id="D",
        name="逆張り型",
        min_score=0.6,
        require_symbols=True,
        allowed_sources=None,
        contrarian=True,
    ),
]
