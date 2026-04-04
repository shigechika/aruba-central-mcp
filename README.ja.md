# aruba-central-mcp

[English](README.md) | 日本語

[Aruba Central](https://www.arubanetworks.com/products/network-management-operations/central/)（GreenLake New Central API）用の MCP サーバーです。

アクセスポイント、スイッチ、無線クライアントの状態を MCP 対応 AI アシスタント（Claude Code、Claude Desktop など）に公開します。

## 機能

- **6つのツール**で Aruba Central インフラを照会:
  - `list_aps` — AP 一覧（サイト・ステータスでフィルタ可能）
  - `list_switches` — スイッチ一覧
  - `list_clients` — 接続中の無線クライアント一覧（SSID・バンドでフィルタ可能）
  - `find_client_by_mac` — MAC アドレスでクライアント検索
  - `get_ap_status` — 特定 AP の詳細ステータス
  - `get_site_summary` — サイト別集約サマリー（AP数・クライアント数）
- **OAuth2 Client Credentials** 認証（GreenLake SSO）
- **自動ページネーション**（大量データ対応）
- **トークン自動リフレッシュ**（期限切れ前に更新）
- 軽量: `mcp` SDK + `httpx` のみ（pandas 不要）

## 前提条件

- Python 3.10 以上
- Aruba Central アカウント（API アクセス権付き）
- OAuth2 クライアント資格情報（クライアント ID とシークレット）

## インストール

```bash
pip install aruba-central-mcp
```

[uv](https://docs.astral.sh/uv/) の場合:

```bash
uvx aruba-central-mcp
```

開発用:

```bash
git clone https://github.com/shigechika/aruba-central-mcp.git
cd aruba-central-mcp
pip install -e ".[test]"
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

### Claude Code

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

## 開発

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/pytest -v
```

## API リファレンス

[GreenLake New Central API](https://developer.arubanetworks.com/) を使用:

- `/network-monitoring/v1/aps` — アクセスポイント
- `/network-monitoring/v1/switches` — スイッチ
- `/network-monitoring/v1/clients` — 無線クライアント

## ライセンス

[MIT](LICENSE)
