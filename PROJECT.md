# PROJECT.md — Anchor Stock

Tài liệu mô tả **hệ thống đang có**: nó làm gì, dữ liệu ra sao, backend cung cấp những gì.
Không chứa quyết định thiết kế — phần đó ở [DESIGN.md](DESIGN.md).

Người đọc dự kiến: bất kỳ ai (người hoặc công cụ) cần hiểu miền dữ liệu trước khi chạm vào giao
diện. Mọi con số trong tài liệu này đọc trực tiếp từ artifact `ae2010a4ad426` trong
`data/artifacts/` và từ `data/reference/sector_map.csv`, không phải ước lượng.

---

## 1. Hệ thống này là gì

**Anchor Stock** theo dõi một rổ **85 cổ phiếu HOSE** và chỉ ra **10 mã "điểm neo"** đại diện cho
cả rổ. Mỗi mã còn lại được gán về đúng một điểm neo — mã có diễn biến giá tương đồng nhất với nó
**sau khi đã trừ đi phần biến động chung của toàn thị trường**.

Phương pháp, một dòng:

```
giá điều chỉnh → log return → hồi quy một nhân tố trên VNINDEX → phần dư E
    → P = corr(E) ∘ corr(E)   (ρ², ma trận 85×85, không âm)
    → tham lam submodular tối đa hoá  F(S) = Σ_i max_{j∈S} P_ij
    → tập điểm neo S, phép gán a(i), độ phủ c_i, đường lợi ích biên Δ
```

Điều quan trọng cho giao diện: **tập điểm neo được tính sẵn theo định kỳ và không tính lại theo
từng phiên.** Giá, khối lượng, chỉ báo kỹ thuật thì cập nhật đến phiên gần nhất thu thập được. Hai
mốc thời gian đó **không trùng nhau** và cả hai đều phải hiện trên màn hình.

Đây là đồ án tốt nghiệp. Bảng chỉ trình bày số liệu đã tính sẵn: không dự báo giá, không tính xác
suất, không đề xuất tỷ trọng danh mục.

---

## 2. Từ vựng

| Thuật ngữ | Ký hiệu | Nghĩa |
|---|---|---|
| Điểm neo | — | Một mã được thuật toán chọn làm đại diện cho một nhóm |
| Nhóm | — | Tập các mã được gán về cùng một điểm neo. 10 nhóm phủ kín 85 mã |
| Độ phủ của một mã | `c_i` | ρ² giữa mã i và điểm neo đại diện cho nó. Trong [0,1] |
| Tổng độ phủ | `F(S)` | Tổng của `c_i` trên cả 85 mã. **Không phải phân số** — hiện là 22.35 |
| Độ phủ trung bình | `F̄(S)` | `F/N`. Trong [0,1] |
| Độ phủ hiệu chỉnh | `F̄_adj` | `(F − k)/(N − k)`. Xem §5 — đây là con số so sánh được |
| Ngưỡng | `τ` | Mức độ phủ tối thiểu để coi là "được đại diện tốt". Hiện `τ = 0.1` |
| Dưới τ | `under_tau` | Mã có `c_i < τ` — điểm neo đại diện **yếu** cho nó. Hiện 33/85 mã |
| Lợi ích biên | `Δ` | Phần `F` tăng thêm khi thêm một điểm neo. Xem §5 — chứa một đơn vị tự phủ |
| Bước chọn | `step_k` | Thứ tự thuật toán chọn mã đó, 1 đến 15 |
| Tương đồng | `ρ²` | Bình phương tương quan giữa hai chuỗi phần dư |
| Phần dư | `E` | Biến động giá sau khi đã trừ phần giải thích được bởi VNINDEX |
| Rổ / vũ trụ | `N` | 85 mã, có thứ tự cố định. Thứ tự này ghim mọi vị trí trong hệ thống |

---

## 3. Lần chạy đang phục vụ — số liệu thật

Artifact `ae2010a4ad426`, `similarity_measure = pearson_rho2`, nguồn dữ liệu VCI.

| Tham số | Giá trị |
|---|---|
| Rổ `N` | 85 mã |
| Cửa sổ ước lượng | 02/01/2025 – 31/12/2025 |
| Số phiên `T` | 249 |
| Chỉ số tham chiếu | VNINDEX |
| Điểm neo công bố `k` | **10** |
| Số bước đã chạy `k_max` | 15 |
| Ngưỡng `τ` | 0.1 |
| Số mã dưới τ | **33 / 85** |
| `F(S)` | 22.349 |
| `F̄(S)` | 0.2629 |
| `F̄_adj` | **0.1646** |

### 10 điểm neo công bố, theo thứ tự thuật toán chọn

| Bước | Mã | Số mã trong nhóm | Δ | `F̄(S)` | `ρ²` TB | `ρ²` nhỏ nhất |
|---|---|---|---|---|---|---|
| 1 | **VIC** | 19 | 5.800 | 0.0682 | 0.140 | 0.009 |
| 2 | **IDI** | 8 | 3.296 | 0.1070 | 0.325 | 0.033 |
| 3 | **PDR** | 15 | 2.907 | 0.1412 | 0.250 | 0.037 |
| 4 | **PVT** | 6 | 1.948 | 0.1641 | 0.327 | 0.053 |
| 5 | **HCM** | 6 | 1.834 | 0.1857 | 0.366 | 0.031 |
| 6 | **SZC** | 5 | 1.529 | 0.2037 | 0.428 | 0.215 |
| 7 | **HSG** | 4 | 1.418 | 0.2204 | 0.444 | 0.018 |
| 8 | **DCM** | 9 | 1.281 | 0.2354 | 0.231 | 0.013 |
| 9 | **CMG** | 7 | 1.176 | 0.2493 | 0.227 | 0.050 |
| 10 | **VIB** | 6 | 1.160 | 0.2629 | 0.267 | 0.011 |

**Kích thước 10 nhóm cộng lại đúng bằng 85.** Đây là một phép phân hoạch kín — nền tảng cho biểu
đồ tỷ trọng ở màn hình điểm neo. Nhóm lớn nhất (VIC, 19 mã) gấp gần 5 lần nhóm nhỏ nhất (HSG, 4 mã).

### 5 bước ngoài tập công bố

`VCG` (11), `FRT` (12), `HDB` (13), `BWE` (14), `VNM` (15).

API vẫn trả về 5 bước này với `in_published_set: false` và **mọi thống kê nhóm bằng null** —
`model_groups` không có dòng nào cho bước chưa công bố. **Giao diện mới không hiển thị chúng**
(quyết định của chủ dự án, xem DESIGN.md §4.3). Việc lọc xảy ra ở phía hiển thị; route không đổi.

### Phân bố ngành của rổ

9 ngành, 18 phân ngành. Nhãn ngành lấy từ `data/reference/sector_map.csv` (nguồn vnstock).

| Ngành | Số mã |
|---|---|
| Bất động sản và Xây dựng | 24 |
| Tài chính | 19 |
| Nguyên vật liệu | 11 |
| Dịch vụ | 11 |
| Hàng tiêu dùng | 6 |
| Nông nghiệp | 5 |
| Năng lượng | 5 |
| Công nghệ | 2 |
| Công nghiệp | 2 |

**Ngành là đối chiếu độc lập, không phải đầu vào.** Nhãn ngành chưa bao giờ đi vào ma trận tương
đồng hay hàm mục tiêu. Việc các nhóm có trùng với ngành hay không là một phép kiểm tra bên ngoài
đối với phương pháp; mô tả nó như thứ mô hình đã dùng sẽ biến phép kiểm tra thành lập luận vòng.

---

## 4. Kiến trúc

```
vnstock (VCI) ──> pipelines/ ──> Supabase Postgres (Singapore)
                                          │
                                          ▼
                            services/api  (FastAPI, Render Web Service)
                                          │  REST, JSON, chỉ đọc
                                          ▼
                            apps/web      (Next.js 15, static export,
                                           Render Static Site)
```

| Thành phần | Ghi chú quan trọng cho giao diện |
|---|---|
| `apps/web` | `output: "export"` — **mọi trang là file HTML tĩnh**, không có render phía máy chủ. Mọi số liệu lấy về từ trình duyệt lúc chạy. Không có route động `[param]`; trang chi tiết dùng query string |
| `services/api` | FastAPI chỉ đọc. Không có ghi, không có xác thực, không có phiên đăng nhập |
| Supabase | Postgres đặt tại Singapore. Độ trễ mạng là lý do các lời gọi API phải chạy **song song**, không nối tiếp |
| Render | `anchor-model-web-lrgg.onrender.com` → tĩnh; `/api/*` rewrite sang `anchor-model-api-lrgg.onrender.com` |

Hệ quả ràng buộc giao diện: **không có đăng nhập, không có trạng thái người dùng lưu trên máy chủ,
không có thao tác ghi.** Mọi thứ trên màn hình là kết quả đọc.

---

## 5. Ba cái bẫy số học phải tôn trọng

Ba chỗ này đã từng bị hiểu sai và đều được ghi lại thành quyết định. Giao diện không được tự ý
diễn giải lại.

**`F`, `F̄` và `F̄_adj` không thay thế nhau.** Mỗi điểm neo tự phủ chính nó ở `ρ²(j,j) = 1`, nên
`F` chứa đúng `k` số hạng bằng 1 không mang thông tin — khoảng 45% của `F`. `F̄ = F/N` vì thế đọc
cao hơn độ phủ thật khoảng 60%. `F̄_adj = (F − k)/(N − k)` đã trừ hết chúng. **Hai con số phải
hiện cùng nhau, không được thay thế nhau** (quyết định D-26). Với lần chạy hiện tại: F̄ = 0.2629
nhưng F̄_adj = 0.1646.

**`Δ` gần bằng 1 nghĩa là gần như không phủ thêm gì.** `Δ` chứa đúng một đơn vị mà mã được chọn
tự phủ chính nó. Ở bước 15, `Δ = 0.9916` — nghĩa là phần phủ thêm cho các mã *khác* **âm nhẹ**.
Nhãn phải nói rõ `Δ` gồm phần tự phủ.

**`F`, `F̄`, `Δ`, `f_j`, `marginal_gain` không bị chặn bởi 1** — chúng là tổng trên nhiều mã. Chỉ
`F̄`, `F̄_adj`, `c_i`, `rho2_mean`, `rho2_min` mới nằm trong [0,1]. Vẽ `F = 22.35` như một thanh
tiến độ phần trăm là sai.

---

## 6. API — những gì backend cung cấp hiện tại

Toàn bộ đường dẫn có tiền tố `/api`. Mọi phản hồi là JSON. Lỗi trả về `{code, message}`.
Định nghĩa kiểu đầy đủ nằm ở [apps/web/src/lib/api.ts](apps/web/src/lib/api.ts) — đó là hợp đồng.

### 6.1 `GET /api/model/active` — lần chạy đang phục vụ

Trả về 25 trường tham số: `run_id`, `artifact_id`, `scope_label`, `similarity_measure`,
`index_symbol`, `window_start`, `window_end`, `latest_session`, `prior_close_date`, `n_sessions`,
`n_tickers`, `q`, `k`, `k_max`, `tau`, `coverage_f`, `coverage_fbar`, `n_under_tau`, `is_primary`,
`created_at`, `loaded_at`.

`window_end` và `latest_session` **cùng có mặt có chủ đích**: điểm neo ước lượng trên một cửa sổ,
còn giá bên cạnh nó chạy đến ngày thu thập gần nhất. Hiện hai mốc cách nhau khoảng 8 tháng.

`F̄_adj` **không nằm trên đường truyền** — nó được tính ở phía client từ `coverage_f`, `k`,
`n_tickers` (hàm `fbarAdjusted` trong `lib/api.ts`).

### 6.2 `GET /api/market/overview` — số liệu phiên

`session_date`, `n_tickers`, `n_with_return`, `advancers`, `decliners`, `unchanged`,
`total_turnover`, `total_volume`, `index_symbol`, `index_close`, `index_ret_1d`.

**Ba con số tăng/đứng/giảm chỉ tính trên các mã CÓ `ret_1d`**, nên chúng không cộng lại thành
`n_tickers`. Mẫu số thật là `n_with_return`. Không được vẽ như một phân hoạch của cả rổ.

### 6.3 `GET /api/market/index-history?range=` — chuỗi chỉ số

`range` ∈ `1m | 3m | 6m | ytd | 1y | all`. Trả `index_symbol`, `range`, `count`, `bars[]` với mỗi
bar là `{bar_date, open, high, low, close, volume, ret_1d}`.

**Một điểm là một PHIÊN, không phải một tick.** Pipeline chỉ thu bar ngày; trong hệ thống này
không tồn tại chuỗi trong phiên. Vì thế **không có khoảng "1D"** và không được tạo ra một cái.

`index_close` là **điểm chỉ số**, không mang đơn vị tiền. Không được quy đổi sang tỷ đồng.

### 6.4 `GET /api/market/movers?direction=&horizon=&limit=` — biến động mạnh

`direction` ∈ `up | down`. `horizon` ∈ `1d | 5d | 1m | 3m | 1y`.

Nhãn hiển thị ánh xạ sang **số phiên**, không phải lịch: `1m` → `ret_20d`, `3m` → `ret_60d`,
`1y` → `ret_252d`. Mỗi dòng trả **cả năm** tỷ suất, nên bảng có thể đổi cột sắp xếp mà không cần
gọi lại.

Mỗi dòng: `ticker`, `company_name`, `sector`, `bar_date`, `close_price`, `volume`,
`turnover_value`, `ret_1d`, `ret_5d`, `ret_20d`, `ret_60d`, `ret_252d`.

`bar_date` là của **riêng dòng đó**. Nếu nó cũ hơn `session_date` thì mã đó đã ngừng giao dịch —
phải đánh dấu, không được để lẫn im lặng trong bảng ghi "phiên hôm nay".

### 6.5 `GET /api/market/liquidity?limit=` — thanh khoản phiên

Cùng hình dạng dòng với `/movers` (cùng một view, chỉ đổi thứ tự sang `turnover_value`).
Trả thêm `session_date` — phiên mà bảng xếp hạng thuộc về.

### 6.6 `GET /api/market/sectors` — đầu vào bản đồ ngành

Mỗi dòng: `sector`, `n_tickers`, `n_with_return`, `mean_ret_1d`, `total_turnover`, `total_volume`.

`sector: null` là **một nhóm thật** (các mã chưa gán ngành), hiển thị là "Khác", không phải lỗi.
`mean_ret_1d: null` là null thật — không có trung bình để báo cáo — phải vẽ trung tính, tuyệt đối
không vẽ bằng màu của 0%.

### 6.7 `GET /api/tickers` — cả rổ

85 dòng, **không phân trang**, theo thứ tự `position` của rổ (không theo bảng chữ cái).

Mỗi dòng: `position`, `ticker`, `company_name`, `sector`, `industry`, `anchor_ticker`,
`coverage_c`, `is_anchor`, `under_tau`, `bar_date`, `ret_1d`.

Đây là toàn bộ dữ liệu cần cho một ô tìm kiếm phía client — không cần gọi API theo từng phím gõ.

### 6.8 `GET /api/tickers/{t}` — một mã

Ba khối:

- `identity` — `ticker`, `company_name`, `sector`, `industry`
- `assignment` — `position`, `anchor_ticker`, `coverage_c`, `is_anchor`, `under_tau`,
  `alpha_hat`, `beta_hat`, `sigma_hat`, `r2`
- `latest` — `bar_date`, OHLCV, cộng **31 chỉ báo** (xem §6.11)

404 khi mã không thuộc rổ của lần chạy đang phục vụ. `latest` có thể null **toàn bộ** trong khi
`identity` và `assignment` vẫn đầy đủ.

### 6.9 `GET /api/tickers/{t}/history?from&to` — chuỗi giá

Không truyền mốc → **252 phiên gần nhất**. Có mốc → mọi dòng trong khoảng, tối đa 2000.
Mỗi bar: `bar_date`, `open`, `high`, `low`, `close`, `volume`, `is_adjusted`.

`from > to` là lỗi 400. Mã lạ là 404. Mã đúng nhưng không có phiên nào trong khoảng là 200 với
mảng rỗng — một lỗi gõ không được trông giống một thị trường im lặng.

### 6.10 `GET /api/tickers/{t}/indicators?from&to` — chuỗi chỉ báo

Cùng quy tắc cửa sổ. Mỗi điểm: `bar_date`, `close`, `volume` cộng **31 chỉ báo**. Mỗi phản hồi tự
đủ, client không phải ghép hai mảng theo ngày.

### 6.11 Ba mươi mốt chỉ báo

Có sẵn ở cả `latest` và chuỗi:

| Nhóm | Trường |
|---|---|
| Trung bình động | `sma_20`, `sma_50`, `sma_200`, `ema_12`, `ema_26` |
| MACD | `macd`, `macd_signal`, `macd_hist` |
| Dao động | `rsi_14`, `stoch_k_14`, `stoch_d_14` |
| Biến động | `atr_14`, `realized_vol_20d`, `realized_vol_60d` |
| Bollinger | `bb_mid_20`, `bb_upper_20`, `bb_lower_20`, `bb_width_20` |
| Khối lượng | `obv`, `volume_sma_20`, `turnover_value` |
| Tỷ suất | `ret_1d`, `ret_5d`, `ret_20d`, `ret_60d`, `ret_ytd` |
| Vị thế | `dist_from_sma_200_pct`, `high_252d`, `low_252d`, `drawdown_from_252d_high` |

**Năm trường là PHÂN SỐ dù tên nghe như phần trăm hay giá**: `bb_width_20`, `realized_vol_20d`,
`realized_vol_60d`, `dist_from_sma_200_pct`, `drawdown_from_252d_high`. `dist_from_sma_200_pct =
0.05` nghĩa là +5%. Còn lại là giá tính bằng **nghìn đồng**, dao động trong [0,100], hoặc số lượng
cổ phiếu.

### 6.12 `GET /api/tickers/{t}/analysis` — nhận định bằng chữ

13 quy tắc, cố định thứ tự. Trả `statements[]` (câu tiếng Việt hoàn chỉnh, hiển thị nguyên văn) và
`skipped[]` (quy tắc không chạy được vì thiếu đầu vào). `statements.length + skipped.length` luôn
bằng 13.

Mã quy tắc: `price_vs_sma_20`, `price_vs_sma_50`, `price_vs_sma_200`, `ma_alignment`, `rsi_band`,
`macd_momentum`, `bollinger_position`, `volume_vs_average`, `range_position`, `ret_5d`, `ret_20d`,
`ret_60d`, `ret_ytd`.

Câu chữ do backend sinh và **hiển thị nguyên văn** — nó phát biểu một sự thật về một con số đã
lưu, không bao giờ mang tính khuyến nghị. Chỗ nào dựa vào quy ước thị trường (dải 70/30 của RSI)
thì câu chữ đã tự gọi đó là quy ước; cắt hay diễn đạt lại sẽ phá vỡ một cam kết của backend.

`skipped` được ghi lại chứ không bị bỏ đi, để **im lặng không bị hiểu nhầm là trung tính**. Giao
diện không hiển thị lý do kỹ thuật; nó hiển thị không gì cả, hoặc "chưa đủ lịch sử" khi cả 13 quy
tắc đều bị bỏ qua.

### 6.13 `GET /api/anchors` — 15 bước chọn

Mỗi dòng: `step_k`, `anchor_ticker`, `position`, `company_name`, `sector`, `marginal_gain`,
`coverage_f`, `coverage_fbar`, `in_published_set`, `size`, `f_j`, `rho2_mean`, `rho2_min`,
`sector_composition`.

Năm bước ngoài tập công bố có `size`, `f_j`, `rho2_mean`, `rho2_min`, `sector_composition`
**bằng null** — đó là sự thật, không phải lỗi ghép bảng.

`sector_composition` **rỗng `{}` với mọi nhóm của artifact hiện tại** — trường này bị hoãn tính
theo thiết kế. Thành phần ngành của một nhóm phải suy ra từ `members[].sector` ở §6.14.

### 6.14 `GET /api/anchors/{a}` — một nhóm

Trả `anchor` (đúng dòng ở §6.13) và `members[]` sắp theo `coverage_c` giảm dần.

Mỗi thành viên: `ticker`, `company_name`, `sector`, `position`, `coverage_c`, `is_anchor`,
`under_tau`, `indicator_date`, `ret_1d`, `ret_5d`, `ret_20d`, `turnover_value`, `rsi_14`,
`dist_from_sma_200_pct`, `drawdown_from_252d_high`.

404 **chỉ khi** mã chưa từng được chọn ở bước nào. Mã được chọn ở bước 11–15 trả 200 với thống kê
null và `members` rỗng.

### 6.15 `GET /api/health`

`status`, `service`, `database`, `time`. Không có màn hình nào dùng — không có thẻ tình trạng
backend trên bảng kết quả.

---

## 7. Đơn vị và quy ước dữ liệu

| Điều | Quy tắc |
|---|---|
| Giá | **nghìn đồng** (quy ước vnstock). VCB đọc là `92.40`, không phải `92,400` |
| `turnover_value`, `total_turnover` | `close × volume`, thừa hưởng đơn vị **nghìn đồng**. Tỷ đồng = nghìn đồng / 1e6 |
| `index_close` | **Điểm chỉ số**, không có đơn vị tiền. Không quy đổi |
| Tỷ suất | **Phân số**, không phải phần trăm. `0.0712` là +7,12% |
| Ngày | ISO `YYYY-MM-DD` trên đường truyền |
| Thiếu dữ liệu | `null` — **không bao giờ là 0**. `ret_252d: null` nghĩa là mã chưa đủ 253 phiên, không phải mã đi ngang cả năm |
| Thứ tự rổ | `position`, cố định. Sắp xếp lại để hiển thị là hành động của người dùng, không phải mặc định |

Quy tắc bao trùm: **null không phải là 0.** Hiện có đúng một chỗ trong mã nguồn thực hiện việc
chuyển đổi mỗi loại — `apps/web/src/components/market/format.ts` — để mỗi phép quy đổi chỉ có một
nơi có thể sai.

---

## 8. Những gì dữ liệu KHÔNG hỗ trợ

Danh sách này tồn tại để giao diện không hứa những thứ backend không có.

- **Không có dữ liệu trong phiên.** Chỉ có bar ngày. Khoảng ngắn nhất trung thực là 1 tháng.
- **Không phải cả sàn HOSE.** 85 mã là một rổ đã chọn, không phải toàn bộ thị trường. Mọi con số
  "toàn thị trường" thực ra là "trên 85 mã này".
- **Ngày mô hình ≠ ngày giá.** Cửa sổ ước lượng kết thúc 31/12/2025; giá chạy đến phiên thu thập
  gần nhất.
- **Giá là giá điều chỉnh**, nên biểu đồ có thể lệch so với biểu đồ giá thô của công ty chứng
  khoán quanh ngày giao dịch không hưởng quyền.
- **Không có dữ liệu khối ngoại**, không có sổ lệnh, không có báo cáo tài chính, không có tin tức.
- **Không có lịch sử nhiều lần chạy trên bảng.** Chỉ một lần chạy đang phục vụ.
- **Không có tài khoản người dùng**, không có danh mục theo dõi, không có cảnh báo. API chỉ đọc.

---

## 9. Đọc thêm

| Tài liệu | Nội dung |
|---|---|
| [DESIGN.md](DESIGN.md) | Yêu cầu thiết kế lại giao diện — tài liệu đi kèm tài liệu này |
| [AGENTS.md](AGENTS.md) | Định hướng repo và quy tắc làm việc |
| `docs/01-data-pipeline.md` | Giá → tỷ suất → mô hình nhân tố → ma trận P |
| `docs/02-algorithm-and-outputs.md` | Hàm mục tiêu tham lam và hợp đồng đầu ra đầy đủ |
| `docs/03-temporal-design.md` | Năm nào chạy, nhánh nghiên cứu và nhánh trực tiếp |
| `docs/04-static-parameters.md` | Một lần chạy đóng băng gì, bảng được phép tính gì từ đó |
| `docs/decisions/` | Các ngã rẽ đã giải quyết, kèm phương án bị loại và lý do |
