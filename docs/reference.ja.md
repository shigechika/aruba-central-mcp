# リファレンス

## `health_check()`

呼び出すたびに以下の5つのキーが必ず存在します。

| キー | 意味 |
|---|---|
| `status` | `healthy` / `degraded` / `error` |
| `service` | 常に `aruba-central-mcp` |
| `version` | パッケージのバージョン |
| `base_url` | 設定済みの `ARUBA_CENTRAL_BASE_URL`（未設定なら空文字列） |
| `auth` | `unknown` / `ok` / `error` / `missing-env` |

`detail` は `degraded` または `error` のときだけ付与され、理由（環境変数の
欠落、または実際の認証失敗時の Aruba Central 側のエラー）が入ります。

軽量な作りです。クライアントを構築して OAuth2 アクセストークンを取得します
（GreenLake SSO、有効なキャッシュがあれば再利用）が、AP・スイッチ・クライア
ントなど他のデータエンドポイントは一切叩きません。セッション開始時やツール
呼び出しがタイムアウトした後に呼んでも安全です。

## ツール一覧

### アクセスポイント

| ツール | 概要 |
|---|---|
| `list_aps(site="", status="")` | アクセスポイント一覧。サイト・ステータスでの絞り込み（サーバー側）に対応 |
| `get_ap_status(ap_name)` | 名前（大文字小文字を区別しない）で指定した1台の詳細ステータス |
| `list_radios(site="", band="")` | AP ラジオ: チャンネル・利用率・ノイズフロア・送信電力 |
| `list_bssids(site="")` | BSSID: どの AP のどのラジオがどの SSID をブロードキャストしているか |
| `list_wlans(site_id="", serial_number="")` | 設定済み WLAN: SSID・帯域・セキュリティ・VLAN |
| `list_swarms(site="")` | AP スワーム/クラスタ: コンダクタ AP・サイト・IP・ファームウェア |
| `get_ap_throughput(serial_number, interface_type="WIRELESS", start_at="", end_at="")` | 1台の AP の TX/RX スループット時系列（既定: 直近3時間） |
| `get_top_aps(usage_type="total", site_id="", limit=10, start_at="", end_at="")` | 帯域使用量トップの AP（`wireless` / `wired` / `total`）、既定は直近24時間 |

### クライアント

| ツール | 概要 |
|---|---|
| `list_clients(ssid="", band="")` | 接続中の無線クライアント一覧。SSID・帯域で絞り込み可能 |
| `find_client_by_mac(mac_address)` | MAC アドレス（無線・有線とも）で1台を直接 API 照会 |
| `get_clients_trend(site_id="", site_name="", start_at="", end_at="", group_by="TYPE", client_type="ALL")` | クライアント数の推移。`TYPE`/`ROLE`/`VLAN`（全種別）または `WLAN`/`RADIO`/`SECURITY`/`PROTOCOL`（無線限定）でグループ化 |
| `get_top_clients_by_usage(site_id="", site_name="", start_at="", end_at="", limit=5)` | 帯域使用量トップのクライアント |
| `get_client_mobility_trail(mac_address, start_at="", end_at="")` | 1台のクライアントのローミング履歴: どの AP に・いつ・どの SSID で接続したか（既定: 直近3時間） |

### インフラ

| ツール | 概要 |
|---|---|
| `list_switches()` | 全スイッチ: 名前・ステータス・モデル・種別・IP・ファームウェア・MAC |
| `get_site_summary()` | サイトごとの AP 台数（オンライン/オフライン）とクライアント数 |

### 朝のパトロール

| ツール | 概要 |
|---|---|
| `health_check()` | サーバーバージョン + バックエンド認証確認のみ。データ取得なし |
| `daily_brief(offline_threshold=10.0)` | 朝の AP ヘルスチェック: オフライン率が `offline_threshold` % を超えたサイトを WARNING として報告。API 障害時は CRITICAL |

## `daily_brief`

全アクセスポイントを `siteName` でバケット分けし、各サイトのオフライン率を
`offline_threshold`（既定 10.0%、厳密に超えた場合のみ、つまりちょうど閾値の
サイトは OK のまま）と比較する1本の Markdown レポートです。バックエンド接続
に失敗した場合はレポート全体が `## CRITICAL — API error: <例外>` になり、
一部のサイトが黙って抜け落ちた部分レポートにはなりません。
`offline_threshold=0.0` を指定すると、オフライン AP が1台でもあるサイトを
すべて WARNING として報告します。

## サーバー側フィルタリング

`list_aps`・`list_clients`・`list_radios`・`list_bssids`・`list_swarms` は
`site` / `ssid` / `band` 引数から [OData v4](https://www.odata.org/) フィル
タを組み立てて Aruba Central 側に送ります。全件取得してローカルで絞り込む
方式ではないので、テナントの規模によらずクエリは軽く済みます。複数ページに
またがりうる一覧（クライアント側の `fetch_all`）はページネーションを自動で
処理します。

## CLI

```bash
aruba-central-mcp            # MCP サーバーを起動（stdio。既定・引数無し）
aruba-central-mcp --version  # バージョンを表示して終了
aruba-central-mcp --help     # 使い方と必須環境変数を表示
aruba-central-mcp --check    # 環境変数と認証を確認して終了
```

`--check` の終了コード: `0` 成功、`1` 必須環境変数の欠落、`2` 認証失敗。
