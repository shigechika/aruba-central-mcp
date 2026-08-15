# セットアップ

## 前提条件

- Python 3.10 以上
- Aruba Central アカウント（API アクセス権付き、GreenLake New Central API）
- OAuth2 クライアント資格情報（クライアント ID とシークレット）

## インストール

```bash
uv pip install aruba-central-mcp
# または
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
uv sync          # または: pip install -e .
```

## API 資格情報の取得方法

1. [HPE GreenLake Platform](https://common.cloud.hpe.com/) にログインします。
2. **Manage Workspace** > **Personal API clients** に移動します。
3. **Create Personal API client** をクリックします。
4. ニックネームを入力し、サービスとして **Aruba Central** を選択します。
5. `client_id` と `client_secret` をコピーします — **シークレットは一度しか
   表示されません**。

詳細は以下を参照してください。

- [OAuth APIs for Access Token](https://developer.arubanetworks.com/hpe-aruba-networking-central/docs/api-oauth-access-token)
- [Making API Calls](https://developer.arubanetworks.com/new-central/docs/making-api-calls)

## 環境変数

| 変数 | 説明 | 例 |
|---|---|---|
| `ARUBA_CENTRAL_BASE_URL` | API ゲートウェイ URL | `apigw-uswest4.central.arubanetworks.com` |
| `ARUBA_CENTRAL_CLIENT_ID` | OAuth2 クライアント ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `ARUBA_CENTRAL_CLIENT_SECRET` | OAuth2 クライアントシークレット | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |

3つとも必須です。いずれか未設定のまま最初に使われるとサーバーがエラーを送出
します。設定ファイルやファイルパス型の環境変数は無く、すべて環境変数だけで
完結するので、プラグイン自身の `.mcp.json` の `env` ブロックにそのまま書けます。

## 何かに組み込む前に確認する

```bash
export ARUBA_CENTRAL_BASE_URL="apigw-uswest4.central.arubanetworks.com"
export ARUBA_CENTRAL_CLIENT_ID="your-client-id"
export ARUBA_CENTRAL_CLIENT_SECRET="your-client-secret"
aruba-central-mcp --check
```

exit `0` なら認証成功、`1` は環境変数の欠落、`2` は認証エラーです。一度これを
走らせておけば、「ツールが何も返さない」が既に答えの出ている問いになります。

## MCP クライアントへの登録

### Claude Code（プラグイン）

このリポジトリはプラグイン 1 個のマーケットプレイスも兼ねています。

```
/plugin marketplace add shigechika/aruba-central-mcp
/plugin install aruba-central-mcp@aruba-central-mcp
```

Claude Code を起動する前に、上記の環境変数3つを export してください。プラグインは
`uvx aruba-central-mcp` を起動し、他の transport と同じ環境変数を読みます。

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

`claude_desktop_config.json` にも同じ `env` ブロックを `command` の下に
書きます。

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

引数無しモードが通常の使い方です。MCP クライアントはこの形で起動します。

## 次に

[リファレンス](reference.ja.md) で全ツール・`health_check` の契約・CLI・
終了コードを扱います。
