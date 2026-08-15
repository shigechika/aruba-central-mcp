# aruba-central-mcp

[Aruba Central](https://www.arubanetworks.com/products/network-management-operations/central/)（GreenLake New Central API）用の MCP サーバーです。

アクセスポイント、スイッチ、無線クライアントの状態を MCP 対応 AI アシスタント
（Claude Code、Claude Desktop など）に STDIO transport 経由で公開します。朝の
`daily_brief` による AP ヘルスチェックと、「この AP はオンラインか」「このクラ
イアントはどこをローミングしたか」を訊かれた瞬間のために作りました。

## 領域別ツール

| 領域 | ツール |
|---|---|
| アクセスポイント | `list_aps`、`get_ap_status`、`list_radios`、`list_bssids`、`list_wlans`、`list_swarms`、`get_ap_throughput`、`get_top_aps` |
| クライアント | `list_clients`、`find_client_by_mac`、`get_clients_trend`、`get_top_clients_by_usage`、`get_client_mobility_trail` |
| インフラ | `list_switches`、`get_site_summary` |
| 朝のパトロール | `health_check`、`daily_brief` |

**すべてのツールが読み取り専用です。** このサーバー経由で Aruba Central 側の
設定が変わることはありません。書き込み経路が存在しないため、状態を変更する
権限を一切与えずに Claude へ渡せます。全ツールの一覧は
[リファレンス](reference.ja.md) を参照してください。

## 設計方針

**OAuth2 Client Credentials のみで、それ以上の権限は持ちません。** 本サーバー
は Personal API client（クライアント ID とシークレット）で GreenLake SSO に
認証し、対話的なユーザーセッションは作りません。取得したトークンは期限が近づく
までキャッシュされます。ユーザー名・パスワードによるログインフローも、アカウ
ントや管理設定に触れるツールもなく、あるのは `/network-monitoring/v1/` の
読み取りエンドポイントだけです。

**クライアント側の全件走査ではなく、サーバー側フィルタリング。** `site`・
`ssid`・`band` を引数に取るツールは OData v4 フィルタを組み立てて Central 側
に送るので、数千台規模のテナントでも絞り込んだクエリは軽く済みます。全件走査
して Python 側でフィルタする作りではありません。長くなりうる一覧はページネー
ションを自動処理します。

**解決済みの MAC やシリアル番号も、URL に載せる前に検証します。**
`find_client_by_mac`・`get_ap_throughput`・`get_client_mobility_trail` は
そのままリクエストパスに入る MAC アドレスやシリアル番号を受け取ります。まず
厳密なパターンで検証し、不正な値は想定外の URL を組み立てる前に明確なエラー
として返します。

## 次に読むもの

- [セットアップ](setup.ja.md) — インストール、GreenLake API 資格情報、環境変数、MCP クライアントへの登録
- [リファレンス](reference.ja.md) — 全ツール・`health_check` の契約・CLI・終了コード
