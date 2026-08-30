# DESIGN.md — Yêu cầu thiết kế lại giao diện Anchor Stock

## 0. Tài liệu này là gì

Đây là **bản mô tả yêu cầu**, không phải hệ thiết kế.

Nó nói: sản phẩm hiện đang là gì, mỗi màn hình đang hỏng chỗ nào, phải mang những khối thông tin
nào, và backend đưa ra dữ liệu gì để lấp đầy chúng.

Nó **không** quyết định bảng màu, cỡ chữ, kiểu biểu đồ, khoảng cách hay bố cục cụ thể. Toàn bộ
phần đó là việc của người thiết kế — xem §7.

Miền dữ liệu, từ vựng và hợp đồng API đầy đủ nằm ở [PROJECT.md](PROJECT.md). Đọc nó trước.

---

## 1. Bối cảnh và người xem

**Anchor Stock** là bảng theo dõi 85 cổ phiếu HOSE, chỉ ra 10 mã "điểm neo" đại diện cho cả rổ và
nhóm cổ phiếu vận động cùng nhau quanh mỗi điểm neo.

Hai nhóm người xem, cùng một màn hình:

- **Hội đồng chấm đồ án.** Cần thấy phương pháp cho ra kết quả gì, và kiểm chứng được các con số.
  Họ sẽ hỏi tới `F̄`, `ρ²`, `τ`, số mã dưới ngưỡng.
- **Người theo dõi thị trường.** Cần thấy phiên hôm nay ra sao, mã nào biến động mạnh, mã mình
  quan tâm đang ở đâu, và mã nào đi cùng nó.

Bảng phải phục vụ nhóm thứ hai trước — kết quả đứng trước, ký hiệu mô hình đứng sau. Nhưng nhóm
thứ nhất không được để mất số liệu nào.

Bối cảnh xem: **màn hình desktop, xem lâu, đọc kỹ.** Không phải trang tiếp thị, không có phễu
chuyển đổi, không có gì để bấm mua. API chỉ đọc, không đăng nhập, không lưu trạng thái người dùng
— **trên toàn bộ sản phẩm không tồn tại một thao tác ghi nào.**

---

## 2. Ràng buộc cứng

Những điều dưới đây đã chốt. Thiết kế làm việc bên trong chúng.

| # | Ràng buộc | Chi tiết |
|---|---|---|
| 1 | **Thương hiệu** | Tên là **Anchor Stock**. Chữ, không có logo hình |
| 2 | **Bộ chữ** | **Roboto** cho chữ, **Roboto Mono** cho số. Đã nạp qua `next/font`, hiện chỉ có 400 và 500 — muốn thêm trọng lượng thì phải nạp thêm, và phải nói rõ |
| 3 | **Chế độ nền** | **Sáng mặc định + nút chuyển sang tối.** Cả hai chế độ phải hoàn chỉnh như nhau. Bộ màu cụ thể là việc của người thiết kế (§7) |
| 4 | **Hướng bảng màu** | Đi theo tinh thần **TradingView**: bảng số dày, màu tiết chế, xanh tăng / đỏ giảm. Giá trị màu chính xác do người thiết kế chốt |
| 5 | **Bề rộng** | Vùng nội dung tối đa **1440px** (hiện là 1280px) |
| 6 | **Thiết bị** | **Chỉ desktop.** Không làm mobile trong đợt này |
| 7 | **Đầu trang** | Giữ **hai tầng**: dòng thương hiệu, rồi thanh tab điều hướng |
| 8 | **Số màn hình** | Đúng **bốn tuyến**: `/`, `/tickers`, `/anchors`, `/about`. Không thêm trang mới. Không có trang giới thiệu kiểu tiếp thị, không có chân trang nhiều cột |
| 9 | **Biểu đồ** | **SVG viết tay**, không dùng thư viện biểu đồ. Các mảnh dựng sẵn liệt kê ở §6 |
| 10 | **Ngôn ngữ** | **Toàn bộ chữ hiển thị bằng tiếng Việt.** Ngoại lệ: tên thương hiệu, mã cổ phiếu, và ký hiệu kỹ thuật không có bản dịch (`RSI`, `MACD`, `F̄`, `ρ²`, `τ`, `Δ`) |
| 11 | **Xuất tĩnh** | Mọi trang là HTML tĩnh; số liệu lấy từ trình duyệt lúc chạy. Không có render phía máy chủ, không có route động — trang chi tiết dùng query string (`?t=VCB`, `?a=VIC`) |
| 12 | **Gọi API song song** | Các lời gọi trên cùng một màn hình phải chồng lấn, không nối tiếp. Cơ sở dữ liệu ở Singapore; bốn lời gọi nối tiếp đo được ~3,9 giây so với ~1,2 giây khi chồng lấn. **Bố cục không được ép một khối chờ khối khác tải xong** |

---

## 3. Bốn màn hình — hiện trạng và việc phải làm

### 3.1 Khung ứng dụng

**Đang có.** Đầu trang hai tầng dính trên cùng: tầng một là chữ "Anchor Model" + phụ đề "Mô hình
điểm neo — HOSE" bên trái, nút đổi nền bên phải; tầng hai là bốn tab. Dưới đó là tiêu đề trang
`<h1>`. Cuối mỗi trang là dải thông tin nguồn — *"Dữ liệu đến {phiên gần nhất} · 85 mã · 10 điểm
neo"* — cộng một khối `<details>` "Chi tiết mô hình" chứa 8 tham số.

**Việc phải làm.**

- Đổi chữ thương hiệu thành **Anchor Stock**.
- Dải thông tin nguồn hiện là dòng chữ nhỏ dễ bỏ sót ở cuối trang, nhưng nó mang thứ **bắt buộc
  phải thấy**: ngày mô hình và ngày giá không trùng nhau. Thiết kế lại sao cho người đọc gặp được
  nó, mà không biến nó thành thứ chắn trước giá.
- Tiêu đề `<h1>` hiện lặp lại đúng chữ trên tab đang chọn. Xem có đáng giữ không.

**Dữ liệu.** `GET /api/model/active` (PROJECT.md §6.1). Tám tham số hiện nằm trong khối gập:
cửa sổ ước lượng, số phiên, `τ`, `F̄(S)`, `F̄_adj`, số mã dưới τ, độ đo, mã artifact.

---

### 3.2 `/` — Tổng quan thị trường

Đây là màn hình mới nhất, vừa dựng lại ở giai đoạn P13, và đang chạy đúng. Nó cần đẹp lên chứ
không cần cứu.

**Đang có** — bốn khối xếp dọc:

1. **Dải chỉ số** — một băng ngang: mã chỉ số + mức điểm + `±%` phiên + thanh độ rộng thị trường
   (tăng/đứng/giảm) + giá trị giao dịch + khối lượng + số mã.
2. **Biểu đồ chỉ số** cạnh **bản đồ ngành**, chia theo tỷ lệ 1,72 : 1. Biểu đồ có 6 tab khoảng
   thời gian (1M/3M/6M/YTD/1Y/ALL), vùng tô đóng về mức mở cửa của khoảng, thang giá bên phải,
   chip giá cuối, và crosshair. Bản đồ ngành là treemap theo giá trị giao dịch, tô màu theo
   `mean_ret_1d`.
3. **Bảng biến động mạnh** — 5 tab khoảng (1D/5D/1M/3M/1Y) + nút chọn chiều tăng/giảm, 10 dòng,
   có thanh biên độ nằm trong ô của cột đang xếp hạng.
4. **Bảng thanh khoản** — 10 dòng, tỷ trọng và tỷ trọng luỹ kế trên giá trị giao dịch phiên.

**Việc phải làm.**

- **Bốn khối đang xếp dọc như một tài liệu, không như một bảng điều khiển.** Không có quan hệ nào
  giữa chúng được thể hiện. Ở bề rộng 1440px có chỗ để tổ chức lại.
- **Bảng biến động mạnh và bảng thanh khoản gần như trùng nhau** — cùng một hình dạng dòng, cùng
  10 dòng, xếp chồng lên nhau. Cân nhắc gộp thành một khối có tab.
- **Dải chỉ số là một băng ngang mảnh** nhồi sáu thứ có tầm quan trọng rất khác nhau vào một hàng.
- **Trang chủ không hề nhắc tới điểm neo** — mà đó là toàn bộ nội dung của sản phẩm. Người vào lần
  đầu không có cách nào biết bảng này khác một bảng giá thông thường ở chỗ nào. *Đây là gợi ý, không
  phải yêu cầu bắt buộc.*

**Dữ liệu.** `GET /api/market/overview`, `/index-history?range=`, `/sectors`,
`/movers?direction=&horizon=&limit=`, `/liquidity?limit=` (PROJECT.md §6.2–6.6). Năm lời gọi, chạy
song song.

**Ba chỗ dữ liệu dễ vẽ sai:**

- Tăng/đứng/giảm **chỉ tính trên các mã có `ret_1d`**, không cộng lại thành 85. Đừng vẽ như một
  phân hoạch của cả rổ.
- `mean_ret_1d: null` của một ngành là null thật, phải vẽ trung tính — **không được vẽ bằng màu
  của 0%**.
- Chuỗi chỉ số **một điểm là một phiên**. Không có dữ liệu trong phiên, nên **không có khoảng
  "1D"**.

---

### 3.3 `/tickers` — Cổ phiếu ⟵ trọng tâm

**Đang có, và đây là màn hình hỏng nhất.**

Vào trang thì gặp một ô tìm kiếm, rồi **một bảng 85 dòng đổ thẳng xuống** — mã, tên công ty,
ngành, điểm neo, độ phủ, `±%` phiên. Bấm vào một mã thì cả danh sách **biến mất**, thay bằng một
liên kết "← Tất cả cổ phiếu" và trang chi tiết. Muốn xem mã khác thì quay lại, cuộn lại, tìm lại.

Trang chi tiết hiện gồm: tên mã + ngành, **6 thẻ số** (giá đóng cửa, thay đổi phiên, giá trị giao
dịch, khối lượng, so với đỉnh 252 phiên, ngày phiên), một **thẻ nhóm điểm neo** viết bằng câu văn,
**biểu đồ giá + khối lượng**, **biểu đồ kỹ thuật tổng hợp**, và **danh sách nhận định** dạng gạch
đầu dòng.

**Việc phải làm.**

- **Bỏ hẳn mảng 85 dòng đổ dọc.** Một danh sách dài như thế không phải là cách vào một màn hình
  chi tiết.
- **Vào trang là đã mở sẵn một mã**, không phải một danh sách. Người dùng đổi mã **qua ô tìm
  kiếm**. Mã mặc định là **`VIC`** — điểm neo bước 1, nhóm lớn nhất với 19/85 mã (§9 mục 1).
- **Ô tìm kiếm phải luôn ở đó**, kể cả khi đang xem chi tiết. Đổi mã là một thao tác, không phải
  ba. Nó lọc theo mã, tên công ty và ngành, lọc ngay trong trình duyệt — cả 85 dòng đã nằm sẵn
  trong bộ nhớ, không tốn lời gọi nào.
- **Hai biểu đồ phải vẽ lại hoàn toàn.** Đây là màn hình mà người ta ở lại lâu nhất, và biểu đồ ở
  đây hiện thô hơn hẳn biểu đồ chỉ số ở trang chủ. Chúng phải đẹp bằng hoặc hơn.
- **31 chỉ báo đang có, biểu đồ hiện chỉ dùng vài cái.** Xem PROJECT.md §6.11 và xét xem nên bày
  thêm gì — và bày ra sao để không thành một bức tường số.
- **Thẻ nhóm điểm neo đang là một câu văn xuôi.** Đây là chỗ duy nhất trên toàn bộ sản phẩm nối
  một cổ phiếu với đóng góp của đồ án. Nó xứng đáng hơn một câu.
- **Danh sách nhận định là 13 gạch đầu dòng không phân cấp**, mọi câu nặng như nhau.

**Dữ liệu.** `GET /api/tickers` (cả 85 dòng, một lần, cho ô tìm kiếm), rồi bốn lời gọi **song
song** cho mã đang mở: `/api/tickers/{t}`, `/{t}/history`, `/{t}/indicators`, `/{t}/analysis`
(PROJECT.md §6.7–6.12).

**Bốn chỗ dữ liệu dễ vẽ sai:**

- `/history` không truyền mốc trả **252 phiên gần nhất**. Muốn khoảng khác thì truyền `from`/`to`
  — nghĩa là một hàng tab khoảng thời gian ở đây là **gọi lại API**, không phải lọc tại chỗ như
  bảng biến động.
- `dist_from_sma_200_pct` và `drawdown_from_252d_high` là **phân số** dù tên nghe như phần trăm.
  `0.05` là +5%.
- `latest` có thể **null toàn bộ** trong khi tên mã và phép gán vẫn đầy đủ.
- Câu nhận định **hiển thị nguyên văn**, không cắt, không diễn đạt lại. Quy tắc bị bỏ qua vì thiếu
  đầu vào thì không hiện lý do kỹ thuật; cả 13 quy tắc đều bỏ qua thì nói "chưa đủ lịch sử".

---

### 3.4 `/anchors` — Điểm neo ⟵ trọng tâm

**Đang có.** Một hàng 10 chip mã, rồi một bảng tóm tắt 4 cột (mã, tên công ty, ngành, số mã đại
diện), rồi một khối gập *"5 mã được chọn tiếp theo (chưa công bố)"*. Chọn một chip thì hiện thêm:
thành phần ngành của nhóm vẽ bằng thanh ngang, bảng thành viên 8 cột, và một khối gập "Chỉ số
nhóm" chứa 9 con số mô hình.

**Việc phải làm.**

- **Bỏ hẳn 5 mã chưa công bố.** Sản phẩm công bố 10 điểm neo. API vẫn trả về 15 bước với cờ
  `in_published_set`; việc lọc xảy ra ở phía hiển thị và route không đổi.
- **Thêm biểu đồ tỷ trọng** — dạng tròn / vành khuyên — cho thấy **mỗi điểm neo đại diện bao nhiêu
  mã trong 85**. Đây là phân hoạch kín và cộng lại đúng 85, nên biểu đồ tròn là trung thực ở đây:

  | VIC | PDR | DCM | IDI | CMG | HCM | PVT | VIB | SZC | HSG |
  |---|---|---|---|---|---|---|---|---|---|
  | 19 | 15 | 9 | 8 | 7 | 6 | 6 | 6 | 5 | 4 |

  Nhóm lớn nhất gấp gần 5 lần nhóm nhỏ nhất. Đây là kết quả đáng chú ý nhất của cả mô hình và hiện
  chưa được nhìn thấy ở đâu.
- **Thiết kế lại danh sách điểm neo.** Hàng chip cộng bảng 4 cột đang nói cùng một thứ hai lần.
- Chọn một điểm neo hiện là chuyển tuyến (`?a=VIC`) và nội dung mọc thêm ở dưới. Xem xét lại cách
  chuyển giữa 10 nhóm.
- **Thành phần ngành là bằng chứng đối chiếu, không phải đầu vào.** Ngành chưa bao giờ đi vào mô
  hình. Nếu các nhóm có trùng ngành thì đó là một phép kiểm tra độc lập — trình bày sao cho không
  ai hiểu nhầm rằng mô hình đã dùng ngành.
- **Chín con số mô hình đang nằm sau một khối gập.** Hội đồng chấm sẽ hỏi tới chúng. Đúng là chúng
  không nên đứng trước danh sách nhóm, nhưng "gập lại" không phải là câu trả lời duy nhất.

**Dữ liệu.** `GET /api/anchors` (15 bước, lọc còn 10), `GET /api/anchors/{a}` cho nhóm đang mở, và
`GET /api/model/active` để lấy `N` — `F̄_adj` cần nó và không có sẵn trên đường truyền
(PROJECT.md §6.13–6.14).

**Ba chỗ dữ liệu dễ vẽ sai:**

- `sector_composition` **rỗng `{}` với mọi nhóm**. Thành phần ngành phải suy ra từ
  `members[].sector`.
- `F(S) = 22.35` và `Δ` **không phải phân số**, không bị chặn bởi 1. Vẽ chúng như thanh phần trăm
  là sai. Chỉ `F̄`, `F̄_adj`, `c_i`, `rho2_mean`, `rho2_min` mới nằm trong [0,1].
- `F̄` và `F̄_adj` **phải hiện cùng nhau**. `F̄ = 0.2629` nhưng `F̄_adj = 0.1646`; chênh lệch là
  phần mỗi điểm neo tự phủ chính nó. Hiện một mình `F̄` là phóng đại độ phủ khoảng 60%.

---

### 3.5 `/about` — Giới thiệu

**Đang có.** Ba khối chữ: "Hệ thống này là gì" (3 đoạn), "Những gì trang này không làm" (1 đoạn),
"Tham số của lần chạy đang dùng" (bảng định nghĩa 13 dòng).

**Việc phải làm.** Không đổi nội dung. Đây là trang duy nhất có văn xuôi dài trong khi ba trang
kia toàn bảng số — nó cần được kéo vào cùng một ngôn ngữ thị giác chứ không trông như đến từ một
sản phẩm khác. Bảng 13 tham số là nơi hội đồng chấm sẽ dừng lại lâu nhất.

**Dữ liệu.** `GET /api/model/active`.

---

## 4. Quy ước hiển thị

| Loại | Quy tắc | Hiện tại |
|---|---|---|
| Số | **`1,234.56`** — dấu phẩy ngăn nghìn, dấu chấm thập phân | Đang là `1.234,56` (locale `vi-VN`). **Phải đổi** |
| Tiền — tổng toàn rổ | Đơn vị **nghìn tỷ đồng** | Đang là tỷ đồng. **Phải đổi** (§9 mục 2) |
| Tiền — từng dòng bảng | Đơn vị **tỷ đồng** | Đúng rồi, giữ. Ở nghìn tỷ cả cột sẽ thành dãy số 0 phẩy |
| Ngày | **`DD/MM/YY`** | Đang là `DD/MM/YYYY`. **Phải đổi** |
| Ngày — bảng tham số `/about` | **`DD/MM/YYYY`**, giữ đủ bốn chữ số năm | Đúng rồi, giữ. Ở bảng đó ranh giới năm chính là thứ đang được nói tới (§9 mục 3) |
| Tỷ suất | Backend gửi **phân số**; đổi sang phần trăm ở đúng một chỗ trong mã nguồn | Đúng rồi, giữ |
| Thiếu dữ liệu | Gạch ngang `—`, **không bao giờ là `0`** | Đúng rồi, giữ |
| Cột số | Chữ số đều bề rộng (`tabular-nums`), căn phải | Đúng rồi, giữ |
| Giá | Đơn vị **nghìn đồng** — VCB đọc là `92.40` | Đúng rồi, giữ |

Xanh và đỏ trong hệ này mang nghĩa **chiều biến động giá**, xuất hiện trên chữ số và nét vẽ.

Một lưu ý kỹ thuật về màu chữ so với màu nét: `#089981` (xanh TradingView) đo được **3,57 : 1**
trên nền trắng — đạt cho một nét vẽ 1,5px, **trượt chuẩn AA cho chữ 13px**, mà chữ 13px là thứ
bảng biến động đặt màu đó lên ở gần như mọi dòng. Hệ hiện tại vì thế giữ **hai bậc màu cho mỗi
chiều**: một bậc cho chữ, một bậc cho nét vẽ và ô treemap. Bảng màu mới cần giải quyết cùng vấn
đề đó, bằng cách nào là tuỳ người thiết kế.

---

## 5. Trạng thái mọi khối đều phải có

Mỗi khối tự gọi API của mình và tự hiển thị trạng thái của mình. Một khối chậm không được che một
khối đã xong.

| Trạng thái | Khi nào | Hiện tại |
|---|---|---|
| Đang tải | Chưa có phản hồi | Khung xương nhấp nháy, có nhãn |
| Lỗi | API trả lỗi hoặc mạng hỏng | Thẻ đỏ nhạt kèm mã lỗi |
| Rỗng | Gọi thành công, không có dòng nào | Câu nói rõ phạm vi nào rỗng |
| Dữ liệu cũ | `bar_date` của dòng cũ hơn phiên đang xét | Huy hiệu trên dòng đó |
| Không phải phiên giao dịch | Ngày không có bar | Ghi chú |
| Dữ liệu giả lập | Chạy cục bộ, chưa cấu hình API | Băng cảnh báo trên đầu trang |

Trạng thái cuối chỉ xuất hiện khi chạy máy cá nhân. Bản triển khai **không bao giờ** dựng dữ liệu
giả — thiếu cấu hình là hiện lỗi, không phải hiện số bịa.

---

## 6. Những gì đã có sẵn để dùng lại

Đừng dựng lại những thứ này từ đầu — chúng đã có và đã chạy đúng.

| Mảnh | Đường dẫn | Làm gì |
|---|---|---|
| Token thiết kế + khung ứng dụng | `apps/web/src/app/globals.css` | Toàn bộ biến màu, chữ, khoảng cách, bo góc, bóng đổ; đầu trang; thanh tab; ô nội dung. **Chỗ để thay bảng màu là ở đây** |
| Kiểu chung của màn hình | `apps/web/src/components/ui.module.css` | Bảng, thẻ, huy hiệu, chip, khối gập |
| Kiểu trang chủ | `apps/web/src/components/market/MarketHome.module.css` | Khối, tab, phân đoạn, thanh trong ô |
| Khung biểu đồ | `components/charts/ChartFrame` `ChartSvg` `ChartAxisLabel` `ChartCaption` `ChartLegend` `ChartNotice` | Vỏ, trục, chú thích, ghi chú của một biểu đồ |
| Crosshair | `components/charts/ChartHover` | Rê chuột **và điều khiển bằng bàn phím**. Dùng lại thì được cả hai |
| Biểu đồ giá | `components/charts/PriceHistoryChart` | Giá + khối lượng. **Vẽ lại** |
| Biểu đồ kỹ thuật | `components/charts/CombinedIndicatorChart` | MA, RSI, dải. **Vẽ lại** |
| Treemap | `components/charts/treemap.ts` | Thuật toán xếp ô vuông hoá |
| Trạng thái | `components/states/` | Sáu trạng thái ở §5 |
| Định dạng | `components/market/format.ts` | Số, phần trăm, ngày, tiền, lớp dấu. **Đây là nơi duy nhất đổi quy ước ở §4.** Hai quyết định ở §9 làm file này mọc thêm một bộ hàm thứ hai: một cho tiền ở mức tổng và một ở mức dòng, một cho ngày phiên và một cho bảng tham số |

Kiểu viết CSS hiện tại: **CSS Modules cho từng thành phần**, token dùng chung khai báo trong
`globals.css`. Thành phần chỉ được dùng `var(--*)`, không bao giờ viết mã màu trực tiếp. Chính chỗ
gián tiếp đó là lý do lần đổi bảng màu trước chỉ là sửa vài dòng khai báo thay vì viết lại từng
thành phần — nên giữ.

---

## 7. Những gì người thiết kế toàn quyền quyết

- Giá trị màu chính xác của cả hai chế độ sáng và tối, và cách chúng ánh xạ sang vai trò
- Thang cỡ chữ, độ đậm, giãn dòng, giãn chữ trong phạm vi bộ Roboto
- Khoảng cách, nhịp, mật độ, cách chia lưới trong bề rộng 1440px
- Bố cục từng màn hình: khối nào cạnh khối nào, cái gì trong thẻ, cái gì trần
- Kiểu biểu đồ: nét, vùng tô, lưới, trục, chú giải, cách hiện giá trị khi rê chuột
- Cách trình bày bảng: mật độ dòng, kẻ chia, đầu cột, cách đánh dấu cột đang xếp hạng
- Huy hiệu, chip, khối gập, ô tìm kiếm, tab, nút chuyển nền — hình dáng của tất cả
- Biểu tượng nếu có (hiện chưa dùng bộ biểu tượng nào)
- Cách trình bày sáu trạng thái ở §5
- Bo góc, bóng đổ, đường kẻ mảnh, chuyển động

---

## 8. Bàn giao mong đợi

1. **Bộ token** — màu, chữ, khoảng cách, bo góc, bóng đổ; đủ cả hai chế độ sáng và tối, dưới dạng
   ánh xạ được sang biến CSS trong `globals.css`.
2. **Bản dựng bốn màn hình** ở bề rộng 1440px, cả hai chế độ nền: `/`, `/tickers` (mở sẵn `VIC`),
   `/anchors` (mở sẵn nhóm `VIC`, 19 mã — nhóm lớn nhất), `/about`.
3. **Bản dựng các khối lặp lại**: một bảng, một biểu đồ, một thẻ số, một huy hiệu, sáu trạng thái
   ở §5.
4. **Ghi chú về biểu đồ** — đủ chi tiết để dựng lại bằng SVG viết tay: nét, lưới, trục, hành vi
   khi rê chuột.

Sau khi có bộ trên, phần dựng mã sẽ thay bảng token trong `globals.css` và viết lại lớp thành phần
theo nó.

---

## 9. Ba điểm đã chốt

Ba câu hỏi này từng để ngỏ và đã được chủ dự án trả lời. Ghi lại kèm phương án bị loại, để lần sau
không phải suy luận lại từ đầu.

**1. Mã mặc định của `/tickers` là `VIC`.** Không phải mã đầu tiên theo thứ tự rổ — thứ tự đó xếp
theo bảng chữ cái nên vị trí đầu là **AAA**, một mã vốn hoá nhỏ, không tiêu biểu cho bất cứ điều gì
mà bảng này nói. `VIC` là điểm neo được thuật toán chọn ở **bước 1** và đại diện cho nhóm lớn nhất
(**19 / 85 mã**), nên mở sẵn nó là mở sẵn kết quả trung tâm của mô hình. Phương án còn lại — mã
thanh khoản cao nhất phiên — bị loại vì nó **đổi theo ngày**, khiến màn hình mặc định không ổn định
và không thể chụp lại để đối chiếu.

**2. Nghìn tỷ cho tổng toàn rổ, tỷ cho từng dòng trong bảng.** Đơn vị nghìn tỷ đọc tốt ở mức tổng.
Ở mức một mã thì không: mã thanh khoản cao nhất trong lần đo gần nhất là VIC ở `860` tỷ — tức
`0.86` nghìn tỷ — và phần còn lại của bảng nhỏ hơn thế nhiều, nên cả cột sẽ thành một dãy số 0
phẩy. Hai đơn vị cùng tồn tại, và **mỗi nơi hiển thị phải ghi rõ đơn vị của nó**.

**3. `DD/MM/YY` ở mọi nơi, trừ bảng tham số của lần chạy ở `/about` giữ đủ bốn chữ số năm.** Năm
hai chữ số hợp với ngày phiên, nơi năm gần như không bao giờ là thứ đang được hỏi. Nhưng cửa sổ ước
lượng đọc thành `02/01/25 – 31/12/25`, và ở đó ranh giới năm **chính là** thứ đang được nói tới —
đó là bảng hội đồng chấm sẽ dừng lại lâu nhất.
