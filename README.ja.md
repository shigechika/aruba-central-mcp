# aruba-central-mcp

[English](README.md) | 日本語

[Aruba Central](https://www.arubanetworks.com/products/network-management-operations/central/)（GreenLake New Central API）用の MCP サーバーです。

アクセスポイント、スイッチ、無線クライアントの状態を MCP 対応 AI アシスタント（Claude Code、Claude Desktop など）に公開します。

ドキュメント: <https://shigechika.github.io/aruba-central-mcp/ja/>

## 機能

### アクセスポイント

| ツール | 説明 |
|--------|------|
| `list_aps` | AP 一覧（サイト・ステータスでフィルタ可能） |
| `list_radios` | AP ラジオ一覧（チャンネル・利用率・ノイズフロア・送信電力） |
| `list_bssids` | BSSID 一覧 |
| `list_wlans` | WLAN 一覧（SSID・セキュリティ・VLAN） |
| `list_swarms` | AP スワーム / クラスタ一覧 |
| `get_ap_status` | 特定 AP の詳細ステータス |
| `get_ap_throughput` | AP スループット推移（TX/RX） |
| `get_top_aps` | 帯域使用量 Top AP（無線/有線/合計） |

### クライアント

| ツール | 説明 |
|--------|------|
| `list_clients` | 接続中の無線クライアント一覧（SSID・バンドでフィルタ可能） |
| `find_client_by_mac` | MAC アドレスでクライアント検索（直接 API ルックアップ） |
| `get_clients_trend` | クライアント数推移 |
| `get_top_clients_by_usage` | 帯域使用量 Top クライアント |
| `get_client_mobility_trail` | クライアントローミング履歴 |

### インフラ

| ツール | 説明 |
|--------|------|
| `list_switches` | スイッチ一覧 |
| `get_site_summary` | サイト別集約サマリー（AP 数・クライアント数） |
| `health_check` | サーバーバージョンの報告と Aruba Central 認証の確認（データ取得なし） |

### 特徴

- **サーバー側 OData フィルタリング**による効率的なクエリ
- **OAuth2 Client Credentials** 認証（GreenLake SSO）
- **自動ページネーション**（大量データ対応）
- **トークン自動リフレッシュ**（期限切れ前に更新）
- 軽量: `mcp` SDK + `httpx` のみ（pandas 不要）

## 前提条件

- Python 3.10 以上
- Aruba Central アカウント（API アクセス権付き）
- OAuth2 クライアント資格情報（クライアント ID とシークレット）

## セットアップ

```bash
# uv
uv pip install aruba-central-mcp

# pip
pip install aruba-central-mcp
```

インストールせずに実行:

```bash
uvx aruba-central-mcp
```

ソースから:

```bash
git clone https://github.com/shigechika/aruba-central-mcp.git
cd aruba-central-mcp

# uv
uv sync

# pip
pip install -e .
```

## 設定

以下の環境変数を設定してください:

| 変数 | 説明 | 例 |
|---|---|---|
| `ARUBA_CENTRAL_BASE_URL` | API ゲートウェイ URL | `apigw-uswest4.central.arubanetworks.com` |
| `ARUBA_CENTRAL_CLIENT_ID` | OAuth2 クライアント ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `ARUBA_CENTRAL_CLIENT_SECRET` | OAuth2 クライアントシークレット | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |

### API 資格情報の取得方法

1. [HPE GreenLake Platform](https://common.cloud.hpe.com/) にログイン
2. **Manage Workspace** > **Personal API clients** に移動
3. **Create Personal API client** をクリック
4. ニックネームを入力し、サービスとして **Aruba Central** を選択
5. `client_id` と `client_secret` をコピー — **シークレットは一度しか表示されません**

詳細は以下を参照:
- [OAuth APIs for Access Token](https://developer.arubanetworks.com/hpe-aruba-networking-central/docs/api-oauth-access-token)
- [Making API Calls](https://developer.arubanetworks.com/new-central/docs/making-api-calls)

## 使い方

### Claude Code（プラグイン）

このリポジトリはプラグイン 1 個のマーケットプレイスも兼ねているので、Claude Code
から直接インストールできます。

```
/plugin marketplace add shigechika/aruba-central-mcp
/plugin install aruba-central-mcp@aruba-central-mcp
```

プラグインは `uvx aruba-central-mcp` を起動し、[設定](#設定)に記載した3つの
環境変数を読みます。Claude Code を起動する前に export しておいてください。

プラグインは `uvx` を起動するため、Claude Code を実行するプロセスの `PATH` に
`uvx` が通っている必要があります。ログインシェルなら通常問題ありませんが、
GUI から起動した場合は通っていないことがあります。プラグインが起動しない場合は
[uv](https://docs.astral.sh/uv/) をシステム全体にインストールしてください。

### Claude Code（手動）

```bash
claude mcp add aruba-central \
  -e ARUBA_CENTRAL_BASE_URL=apigw-uswest4.central.arubanetworks.com \
  -e ARUBA_CENTRAL_CLIENT_ID=your-client-id \
  -e ARUBA_CENTRAL_CLIENT_SECRET=your-client-secret \
  -- uvx aruba-central-mcp
```

または `.mcp.json` に追加:

```json
{
  "mcpServers": {
    "aruba-central": {
      "command": "uvx",
      "args": ["aruba-central-mcp"],
      "env": {
        "ARUBA_CENTRAL_BASE_URL": "apigw-uswest4.central.arubanetworks.com",
        "ARUBA_CENTRAL_CLIENT_ID": "your-client-id",
        "ARUBA_CENTRAL_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

### Claude Desktop

`claude_desktop_config.json` に追加:

```json
{
  "mcpServers": {
    "aruba-central": {
      "command": "uvx",
      "args": ["aruba-central-mcp"],
      "env": {
        "ARUBA_CENTRAL_BASE_URL": "apigw-uswest4.central.arubanetworks.com",
        "ARUBA_CENTRAL_CLIENT_ID": "your-client-id",
        "ARUBA_CENTRAL_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

### 直接実行

```bash
export ARUBA_CENTRAL_BASE_URL="apigw-uswest4.central.arubanetworks.com"
export ARUBA_CENTRAL_CLIENT_ID="your-client-id"
export ARUBA_CENTRAL_CLIENT_SECRET="your-client-secret"
python3 -m aruba_central_mcp
```

### CLI オプション

```bash
aruba-central-mcp --version   # バージョン表示して終了
aruba-central-mcp --help      # 使い方と必須環境変数を表示
aruba-central-mcp --check     # 環境変数と OAuth2 認証を検証して終了
aruba-central-mcp             # MCP サーバー起動（STDIO、デフォルト）
```

オプション無指定の場合は MCP STDIO サーバーとして動作します（MCP クライアントから使うモード）。

`--check` の exit code: `0` 成功、`1` 設定エラー、`2` 認証エラー。

## 開発

```bash
git clone https://github.com/shigechika/aruba-central-mcp.git
cd aruba-central-mcp

# uv
uv sync --dev
uv run pytest -v

# pip
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest -v
```

### ライブスモークテスト

ユニットテストは Central をトランスポート層でモックする。それが速さの理由であり、
同時に「ツールが実データを返さなくなったこと」を検出できない理由でもある。
`scripts/smoke_test.py` は設定済みのテナントに対して**登録されている全ツール**を
実行し、空・不正・エラー応答を失敗として報告する。

```bash
# サーバーと同じ ARUBA_CENTRAL_* 環境変数が必要
uv run python scripts/smoke_test.py
uv run python scripts/smoke_test.py --only radios --traceback
```

- **読み取り専用**。ここにあるツールは全て読み取りのみで、Central の設定は変更しない。
  将来書き込むツールを追加する場合は state-changing として列挙しスキップする（テストで強制）。
- **レポートにペイロードを出さない**。ツール名・ステータス・件数のみ。エラー文言は
  問い合わせた機器名・クライアント MAC・サイト名を含むため伏字にする。
- **ネットワーク固有の値を spec に書かない**。機器単位のツールが必要とする AP 名・
  シリアル番号・クライアント MAC は一覧から実行時に発見し、対象が無ければスキップする。
  2本のテストで担保: 該当パラメータの直値を拒否し、アドレス的な形がファイル内に
  現れることを禁じる（公開リポジトリのため）。
- 一覧系と時系列系は空応答でも合格とする（swarm 未設定のサイトは実在する構成）。
  ただし直前に発見した名前で引く**ルックアップ**が空を返すのは不正なので、
  そちらの probe は明示的に拒否する。
- CI では安価な半分を強制する。probe spec の無いツールを登録するとビルドが失敗するので
  （`tests/test_smoke_probes.py`）、ツール追加時に「どうやって動作を確認するか」を必ず決めることになる。
- `scripts/smoke_harness.py` はエンジンであり Central 固有の知識を持たない。このハーネスを
  共有する各サーバーで同一に保つ方針なので、エンジンのバグはこの写しを直すのではなく
  一度直して全体に同期する。

初回実行で実際に1件見つかった。`get_client_mobility_trail` が endpoint の受け付けない
ページサイズを要求しており、全クライアントで失敗していた。

## API リファレンス

[GreenLake New Central API](https://developer.arubanetworks.com/) を使用:

- `/network-monitoring/v1/aps` — アクセスポイント
- `/network-monitoring/v1/radios` — AP ラジオ
- `/network-monitoring/v1/bssids` — BSSID
- `/network-monitoring/v1/wlans` — WLAN
- `/network-monitoring/v1/swarms` — AP スワーム / クラスタ
- `/network-monitoring/v1/switches` — スイッチ
- `/network-monitoring/v1/clients` — クライアント
- `/network-monitoring/v1/clients-trend` — クライアント数推移
- `/network-monitoring/v1/clients-topn-usage` — Top クライアント
- `/network-monitoring/v1/top-aps-by-usage` — Top AP

## ライセンス

[MIT](LICENSE)
