# remotetrade

Polymarket の暗号資産 Up/Down 市場が、数分後の実市場価格に先行するかを検証するためのペーパートレード実験です。

実資金注文は出しません。Polymarket の公開 Gamma API から Up/Down 価格を読み、Coinbase の公開 ticker を現物価格の代替として使い、仮想ポジションと損益を `data/` に記録します。

## セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
```

## 単体実行

```powershell
python -m remotetrade.app --once
```

1回だけシグナルを評価します。

```powershell
python -m remotetrade.app
```

`POLL_SECONDS` 間隔で継続実行します。

## 複数パターン

`patterns.json` に複数の戦略パラメータを定義しています。

- `scalp_fast`: 反応を早めた高回転型
- `balanced`: 標準型
- `strong_only`: 強いオッズ変化だけを使う慎重型

```powershell
python -m remotetrade.app --once --patterns patterns.json
```

各パターンは別々の状態ファイルと取引ログを持ちます。

```text
data/scalp_fast_state.json
data/scalp_fast_trades.csv
data/balanced_state.json
data/balanced_trades.csv
data/strong_only_state.json
data/strong_only_trades.csv
```

## 株式イベント版

記事に近い形で、Polymarket を「イベント期待の参考データ」として読み、関連株をペーパートレードするモードもあります。Polymarket では取引しません。

```powershell
python -m remotetrade.app --once --stock-patterns stock_patterns.json
```

`stock_patterns.json` では、イベントカテゴリごとにロング候補とショート候補を分けています。

例:

- イラン停戦期待上昇: `AAL` / `LUV` ロング、`OXY` ショート
- イラン停戦期待低下: `OXY` ロング、`AAL` / `LUV` ショート
- Fed 利下げ期待上昇: `ARKK` ロング、`BAC` ショート
- Fed 利下げ期待低下: `BAC` ロング、`ARKK` ショート
- 暗号政策/ETF期待上昇: `COIN` / `HOOD` / `MSTR` ロング、`BITI` ショート
- BTC proxy期待上昇: `MSTR` / `MARA` / `RIOT` / `CLSK` ロング、`BITI` ショート
- Stablecoinリスク上昇: `BITI` ロング、`COIN` / `HOOD` / `MSTR` ショート

株価は鍵なしで動かしやすい Stooq の公開CSVから取得します。実運用判断ではなく検証用です。

## Discord通知

`.env` または GitHub Actions secrets に `DISCORD_WEBHOOK_URL` を設定します。

```powershell
python -m remotetrade.app --once --patterns patterns.json --discord
```

取引イベントだけ通知したい場合:

```powershell
python -m remotetrade.app --patterns patterns.json --discord --discord-events-only
```

## GitHub Actions

[paper-trade.yml](.github/workflows/paper-trade.yml) は5分ごとに起動し、暗号資産版はジョブ内で約270秒間、`POLL_SECONDS=15` のペーパートレードを回します。株式イベント版は同じジョブで1 tickだけ評価します。

使うには、GitHub の repository secrets に以下を追加してください。

```text
DISCORD_WEBHOOK_URL
```

Actions の実行環境は毎回消えるため、`data/` は `actions/cache` で引き継ぎます。

## ロジック

- Polymarket の Up/Yes 価格を前回観測値と比較し、短時間のオッズ変化をシグナル化します。
- `odds_delta >= ENTRY_THRESHOLD` なら、数分後の上昇を見込んでロングします。
- `odds_delta <= -ENTRY_THRESHOLD` なら、数分後の下落を見込んでショートします。
- ポジションは `TAKE_PROFIT_PCT`、`STOP_LOSS_PCT`、`HOLD_SECONDS` 経過、または強い逆方向シグナルで閉じます。
- 1回の取引サイズは `min(資金 * RISK_FRACTION, MAX_TRADE_SIZE_USD)` に制限します。

これは仮説検証用のベースラインです。Polymarket の市場ごとのルール、満期、参照価格、流動性、スプレッドを無視すると結果が歪むため、本番判断には使わないでください。
