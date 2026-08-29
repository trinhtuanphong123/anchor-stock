# Project Status Report — starting state of the anchor-model migration

**Ngày khảo sát:** 2026-08-17
**Phạm vi:** toàn repo `D:\DATN_new` trước khi bắt đầu chuyển sang anchor model.

Tài liệu này ghi lại **trạng thái xuất phát**. Nó không được cập nhật theo tiến độ — tiến độ
nằm ở `plans/active/anchor-model-migration.md`. Mục đích là để sau này còn đối chiếu được
"lúc bắt đầu repo thực sự đang ở đâu", vì phần lớn tài liệu cũ mô tả một kiến trúc không còn
tồn tại trên đĩa.

---

## 1 Kết luận cốt lõi

Repo chứa **hai thế giới song song**:

- **Thế giới CŨ — "ClusterWeb"**: Leiden community detection → behavior windows → outcome
  analysis → dashboard snapshots. Chiếm phần lớn hạ tầng điều phối, schema, API và frontend.
- **Thế giới MỚI — anchor model**: log returns → one-factor OLS trên VNINDEX → ma trận ρ² của
  residual → greedy submodular chọn anchor. Đã code sạch nhưng **nằm biệt lập**, không nối vào
  hệ điều phối nào.

Bốn tài liệu đặc tả (`01`–`04` trong thư mục này) mô tả thế giới MỚI và là nguồn chân lý duy nhất.

---

## 2 Thế giới cũ đã chết về mặt kỹ thuật

Không phải "đang chạy và cần thay" — nó **không thể chạy hết**:

| Sự kiện | Bằng chứng |
|---|---|
| `pipelines/clustering/` không tồn tại | `production_registry.adapt_clustering` import `pipelines.clustering.graph_leiden` |
| `pipelines/outcomes/` chỉ có `__init__.py` rỗng | `adapt_outcomes` import `pipelines.outcomes.outcome_analysis` |
| Registry vẫn khai báo cả hai là `AVAILABLE` | nên chain hỏng *bên trong* adapter, không phải ở preflight |
| Stack Leiden không có trong dependency | `requirements.in` không có `leidenalg`, `python-igraph`, `networkx`, `scikit-learn` |

Hệ quả: daily chain (`universe_sync → daily_incremental → feature_daily → behavior_windows →
clustering → outcomes → snapshot_generation`) chết ở stage thứ năm.

---

## 3 Bộ migration không apply được

13 file trên đĩa: `00001`–`00004`, `00009`, `00011`–`00017`.
**Thiếu:** `00005`, `00006`, `00007`, `00008`, `00010` (header của `00009` và `00011` có trích
dẫn `00006_p2s01e_schema_validation.sql`, tức chúng từng tồn tại rồi bị gỡ).

`00012` cấp/thu quyền trên **11 bảng mà không migration nào trên đĩa tạo ra**:

```
cluster_communities   cluster_members      cluster_edges       cluster_outcome_stats
historical_pattern_matches   lead_lag_edges   ticker_current_state
eval_baseline_kmeans  model_runs           model_artifacts     model_outputs
```

cộng với `GRANT USAGE` trên 6 sequence không tồn tại. Nên **không thể apply toàn bộ bộ
migration từ một DB rỗng** — mà Supabase thật đang rỗng hoàn toàn. Đây chính là lý do chọn
reset baseline sạch thay vì migration additive.

---

## 4 Tình trạng theo lớp

| Thành phần | Trạng thái | Ghi chú |
|---|---|---|
| `anchors/greedy.py`, `factor/model.py`, `returns/matrix.py` | Đúng đặc tả, chạy được | numpy thuần, tất định, có assertion nội bộ, có `main()` self-check |
| `anchors/run.py` | Đảo biệt lập | CLI độc lập ghi thẳng `anchor_runs`; không nằm trong chain nào |
| `returns/build.py` | Chạy được | `daily_bars`/`market_index_bars` → `daily_returns`/`index_returns` |
| `ingestion/daily.py`, `index_bars.py`, `staging.py` | Chạy được, nhưng rối | `index_bars` import **3 hàm private** của `daily` rồi cài lại gần y hệt `_fetch_raw_rows` |
| `ingestion/daily_ohlcv.py` | Code chết | dry-run bắt buộc, không ai import, tên cột (`symbol`/`trade_date`) lệch schema thật (`ticker`/`bar_date`) |
| `ingestion/list_stock.txt` | **0 byte, không code nào đọc** | universe thực tế lấy từ bảng `stocks` qua `common/hwm.py:get_active_tickers()` |
| Lớp điều phối (`scheduler`, `production_*`, `bootstrap`) | Không chạy được | xem §2 |
| `services/api` | Chạy được nhưng thuộc thế giới cũ | 16 endpoint; `queries.py` hard-code `ALGO_LEIDEN`; `_freshness_block()` kéo `dashboard_snapshots` + `cluster_runs` vào cả những endpoint vốn trung tính |
| `apps/web` | Chạy độc lập được | `lib/mock.ts` phủ đủ 15 kiểu response; tự chạy mock khi `NEXT_PUBLIC_API_BASE_URL` không cấu hình |

**Bán kính ảnh hưởng khi xoá:** không có gì ngoài `pipelines/` import vào `pipelines.*`
(`apps/`, `services/`, `supabase/` đều sạch). `tests/` ở gốc repo rỗng.

---

## 5 Những thứ tài liệu cũ nhắc tới nhưng không tồn tại

`CLAUDE.md` và các file cấu hình trỏ tới một loạt đường dẫn ma:

```
AGENTS.md              docs/                  docs/WORKFLOW.md      docs/ARCHITECTURE.md
docs/plans/active/     docs/product/          docs/decisions/       docs/deployment/
DATABASE_SCHEMA.md     API_CONTRACT.md        reports/              data/
infra/aws/env/         scripts/schema/        .github/  (không có CI)
```

Không có Airflow ở bất kỳ đâu — chỉ hai câu văn xuôi nhắc tới nó như dự định.

---

## 6 Khoảng cách giữa code hiện có và đặc tả mới

Lõi anchor bám đặc tả rất sát. Cái thiếu là các chiều **nghiên cứu** và **vận hành**:

| Đặc tả yêu cầu | Hiện trạng |
|---|---|
| Run theo từng năm + bảng tần suất + cross-year evaluation (03) | Chưa có; `run.py` chỉ chạy một cửa sổ 365 ngày trượt |
| `scope ∈ {year, live}`, cờ `active`, `similarity_measure` (03 §8, 04 §2) | `anchor_runs` không có cột nào trong số này |
| Lưu σ̂ (01 §8, 04 §2) | `factor_estimates` chỉ có `alpha`, `beta`, `r2` |
| Lưu P (04 §2, §6) | `00017` ghi rõ "P NOT stored" — **mâu thuẫn với đặc tả** |
| dCor² để so sánh (01 §7) | Chưa có; `requirements.in` không có `dcor`/`scipy` |
| Daily apply path, rolling ρ²_W, monitors (04 §3, §4) | Chưa có |
| Chỉ báo kỹ thuật cho dashboard | Chưa có |

---

## 7 Quyết định đã chốt

Xem `plans/active/anchor-model-migration.md` §Quyết định và `decisions/`.
Tóm tắt: gỡ sạch thế giới cũ (trừ frontend), gỡ lớp điều phối tự chế (Airflow thay thế), gỡ
lớp intraday, reset baseline Supabase, chỉ báo kỹ thuật lưu cột tường minh, bỏ ngưỡng tối
thiểu số phiên, universe từ `list_stocks.txt`, và **2021 trở thành năm nghiên cứu thứ 5**.
