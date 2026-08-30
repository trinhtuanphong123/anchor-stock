# MIGRATION.md — đưa design system vào `apps/web`

Chín bước, mỗi bước **một commit** và phải `next dev` chạy được trước khi qua bước sau. Mỗi bước có
một khối prompt dán trực tiếp vào Claude Code.

Nguyên tắc xuyên suốt: **`components.css` là lớp global, CSS Modules là lớp cục bộ.** Class `as-*`
lo hình thức (màu, chữ, viền, mật độ, trạng thái hover/active/focus). Module chỉ còn giữ những gì
DS không nói: grid của riêng một màn hình, tỷ lệ cột, vị trí tuyệt đối. **Module không được chứa mã
màu, không được chứa px thô** — chỉ `var(--*)`.

---

## Bước 0 — Land file, chưa đổi một pixel

Copy vào repo:

```
apps/web/src/styles/ds/
  tokens/{fonts,colors,typography,spacing,radius,elevation,motion,base}.css
  components.css
  ds.css
```

Sửa `ds.css`: **xoá dòng `@import` `fonts.css`** (đã có `next/font`).

Trong `app/globals.css`, dòng đầu tiên:

```css
@import url("../styles/ds/ds.css");
```

Rồi **xoá khỏi `globals.css` mọi khai báo `--*` cũ** ở §1–§8 — chúng bị token mới thay hoàn toàn.
Giữ lại phần nào là layout riêng của app chưa có trong DS.

> **Prompt**
> Tôi vừa thêm `apps/web/src/styles/ds/` — lớp token và lớp class `as-*` của design system Anchor
> Stock. Hãy: (1) thêm `@import url("../styles/ds/ds.css");` lên đầu `app/globals.css`; (2) xoá khỏi
> `globals.css` tất cả khai báo biến CSS trùng tên với token trong `styles/ds/tokens/` — không giữ
> bản sao nào; (3) liệt kê cho tôi những biến `--*` mà `globals.css` đang khai báo nhưng KHÔNG có
> trong bộ token, và những biến mà code đang dùng nhưng không còn ai khai báo. Chưa sửa component
> nào. Chạy `next build` và báo lỗi nếu có.

Kết quả mong đợi: app đổi màu nhẹ (palette đã dọn), không hỏng gì.

---

## Bước 1 — `format.ts`: quy ước hiển thị §4

Đây là bước rẻ nhất và sửa được nhiều lỗi đọc số nhất. Làm trước khi chạm vào bố cục.

| Loại | Phải thành |
|---|---|
| Số | `1,234.56` — phẩy ngăn nghìn, chấm thập phân. Đang là locale `vi-VN` (`1.234,56`) |
| Tiền, tổng toàn rổ | **nghìn tỷ đồng** (đang là tỷ) |
| Tiền, từng dòng bảng | **tỷ đồng** — giữ nguyên |
| Ngày | `DD/MM/YY` (đang `DD/MM/YYYY`) |
| Ngày, bảng tham số `/about` | `DD/MM/YYYY` — giữ đủ bốn chữ số |
| Tỷ suất | backend gửi phân số, đổi sang % ở đúng một chỗ |
| Thiếu dữ liệu | `—` (U+2014), **không bao giờ `0`** |

Hai đơn vị tiền cùng tồn tại, nên **mọi nơi hiển thị phải ghi rõ đơn vị của nó** trong nhãn:
"GT giao dịch (tỷ đ)", "18.42 nghìn tỷ đ".

> **Prompt**
> Sửa `apps/web/src/components/market/format.ts` theo bảng quy ước sau, và chỉ ở file này. Đọc
> `reference/ui_kit/format.js` trong gói handoff làm bản mẫu.
> — số: `1,234.56` (dấu phẩy ngăn nghìn, dấu chấm thập phân) — bỏ locale `vi-VN`;
> — tiền: hai hàm riêng, `formatTrillion` cho tổng toàn rổ (nghìn tỷ đ) và `formatBillion` cho từng
> dòng bảng (tỷ đ);
> — ngày: hai hàm riêng, `formatSession` → `DD/MM/YY` và `formatParamDate` → `DD/MM/YYYY` (chỉ dùng
> cho bảng tham số ở `/about`);
> — giá trị thiếu luôn trả `"—"`, không bao giờ `"0"`.
> Sau đó cập nhật mọi caller. Chú ý: `dist_from_sma_200_pct` và `drawdown_from_252d_high` là **phân
> số** dù tên nghe như phần trăm — `0.05` là `+5%`. Đừng nhân hai lần.

---

## Bước 2 — Khung ứng dụng

Class có sẵn: `as-shell` `as-header` `as-header__top` `as-header__brand` `as-wordmark`
`as-eyebrow` `as-header__actions` `as-tabbar` `as-navtab` `as-navtab--active` `as-well`
`as-page-heading` `as-theme-toggle` `as-provenance` `as-provenance__summary`
`as-provenance__items` `as-provenance__item` `as-provenance__dot`.

Tham chiếu: `reference/components/shell/*.jsx` + `.prompt.md`, và `reference/ui_kit/index.html`.

Việc phải làm (DESIGN.md §3.1):

- Chữ thương hiệu đổi thành **Anchor Stock** (đang là "Anchor Model"). Chữ, không có logo hình.
- Header giữ **hai tầng** và dính cả cụm.
- Dải provenance mang thứ bắt buộc phải thấy: **ngày mô hình và ngày giá không trùng nhau.** Bố
  cục mới cho nó ở `as-provenance` — thấy được nhưng không chắn trước giá.
- Xem lại `<h1>` đang lặp đúng chữ trên tab đang chọn.

> **Prompt**
> Viết lại `AppChrome.tsx`, `ThemeToggle.tsx`, `ProvenanceStrip.tsx` dùng class `as-*` toàn cục
> thay cho CSS Module của chúng. Đọc `reference/components/shell/AppHeader.jsx`,
> `ThemeToggle.jsx`, `ProvenanceStrip.jsx` (kèm `.prompt.md`) để lấy đúng cấu trúc DOM và tên
> class — viết lại thành `.tsx` theo pattern hiện có của repo, không copy file .jsx vào repo.
> Đổi wordmark thành "Anchor Stock". `ThemeToggle` là **chữ** ("Nền tối" / "Nền sáng"), không icon.
> Giữ nguyên logic `[data-theme]` và script chống nháy đang chạy. Sau đó xoá phần CSS Module đã
> thành dư trong các file module tương ứng.

---

## Bước 3 — Sáu trạng thái và các khối lặp lại

Làm trước các màn hình, vì mọi màn hình đều dùng.

| Trạng thái | Class | Khi nào |
|---|---|---|
| Đang tải | `as-skeleton`, `as-spinner` | Chưa có phản hồi. Khung xương nhấp nháy, **có nhãn** |
| Lỗi | `as-notice as-notice--error` | API lỗi hoặc mạng hỏng. Kèm mã lỗi |
| Rỗng | `as-empty` `as-empty__scope` | Gọi được, không dòng nào. Nói rõ **phạm vi nào** rỗng |
| Dữ liệu cũ | `as-badge as-badge--warn`, `⚠` | `bar_date` cũ hơn phiên đang xét. Huy hiệu trên đúng dòng đó |
| Không phải phiên | `as-notice as-notice--muted` | Ngày không có bar |
| Dữ liệu giả lập | `as-notice as-notice--mock` | **Chỉ khi chạy cục bộ.** Bản deploy không bao giờ dựng số giả |

Khối lặp lại: `as-panel` / `as-doc-panel` (hai hình dạng panel, **không gộp**), `as-kpi-grid`
`as-kpi`, `as-stat`, `as-table` (+ `as-num` `as-ranked` `as-rank` `as-barcell` `as-bar-track`
`as-bar-fill`), `as-badge`, `as-chips` `as-chip`, `as-tabs` `as-tab`, `as-segment`,
`as-search` `as-count`, `as-details`, `as-defs` `as-def-term` `as-def-value`, `as-bars`
`as-bar-row`, `as-prose`.

> **Prompt**
> Viết lại `components/states/` (6 trạng thái ở bảng trên) và các khối lặp lại — panel, thẻ số,
> bảng, huy hiệu, chip, tab, segment, ô tìm kiếm, khối gập, danh sách định nghĩa — dùng class
> `as-*`. Đọc `reference/components/feedback/*` và `reference/components/data/*` (mỗi component có
> `.d.ts` cho hợp đồng props và `.prompt.md` cho ví dụ dùng) rồi viết lại thành `.tsx`.
> Hai lưu ý bắt buộc: `as-panel` (panel có thanh đầu, dùng ở bảng thị trường) và `as-doc-panel`
> (hộp có đệm, dùng ở màn hình tài liệu) là **hai thứ khác nhau, không gộp**. Cột số luôn
> `as-num` — `tabular-nums`, căn phải.

---

## Bước 4 — `/` Tổng quan thị trường

Route bạn chọn làm trước, và cũng là route khó nhất — làm sớm để lộ hết thiếu sót của lớp DS.

Mật độ ở đây là **mật độ bảng điều khiển**: dòng 32px, đầu cột 11px chữ hoa có giãn chữ, panel
phân cách bằng đường kẻ mảnh. Chặt hơn hai màn hình tài liệu, và đó là chủ ý.

Chart: `as-chart-frame` `as-chart-svg` `as-chart-grid` `as-chart-series` `as-chart-line`
`as-chart-tick` `as-chart-lasttag` `as-chart-baseline` `as-crosshair-line` `as-crosshair-dot`
`as-tooltip` `as-legend`. Treemap: `as-treemap-wrap` `as-treemap__tile` `as-treemap__label`.
Dải chỉ số: `as-marketbar` `as-symbol` `as-breadth`.

Việc phải làm (DESIGN.md §3.2):

- Bốn khối đang **xếp dọc như một tài liệu**, không như bảng điều khiển. 1440px có chỗ để tổ chức lại.
- **Bảng biến động và bảng thanh khoản gần như trùng nhau** — cùng hình dạng dòng, cùng 10 dòng,
  chồng lên nhau. Gộp thành một khối có tab.
- Dải chỉ số là một băng mảnh nhồi sáu thứ có tầm quan trọng rất khác nhau vào một hàng.
- Trang chủ **không hề nhắc tới điểm neo** — mà đó là toàn bộ nội dung sản phẩm. (Gợi ý, không bắt buộc.)

Ba chỗ dữ liệu dễ vẽ sai:

- Tăng/đứng/giảm **chỉ tính trên mã có `ret_1d`**, không cộng lại thành 85. Đừng vẽ như phân hoạch của cả rổ.
- `mean_ret_1d: null` của một ngành là null thật → vẽ trung tính, **không dùng màu của 0%**.
- Chuỗi chỉ số **một điểm là một phiên**. Không có dữ liệu trong phiên → **không có khoảng "1D"**.

> **Prompt**
> Viết lại màn hình `/` theo `reference/ui_kit/MarketScreen.jsx` — bố cục, mật độ, thứ tự khối,
> tên nhãn tiếng Việt lấy đúng từ đó. Dùng class `as-*`; CSS Module của màn hình này chỉ còn giữ
> grid riêng và tỷ lệ cột, mọi giá trị bằng `var(--*)`.
> Chart vẽ lại theo `reference/components/charts/IndexAreaChart.jsx` và `SectorTreemap.jsx`: SVG
> viết tay, `viewBox` cố định + `vector-effect: non-scaling-stroke`, thang giá **bên phải**, vùng
> tô đóng về **mức mở cửa của khoảng** (có đường baseline nét đứt màu hổ phách), chip giá cuối ghim
> vào thang, crosshair là nét đứt trung tính — **không bao giờ tô màu** — và chạy được **cả bằng
> bàn phím**. Giữ `ChartHover` hiện có nếu nó đã làm đúng cả hai.
> Treemap là ngoại lệ của quy tắc viewBox cố định: nó đo hộp pixel thật, vì không có tỷ lệ khung
> nội tại và nhãn phải so với cỡ chữ.
> Gộp bảng biến động và bảng thanh khoản thành một panel có tab. Giữ 5 lời gọi API **song song**,
> mỗi khối tự quản trạng thái của mình — một khối chậm không được làm trắng khối đã xong.
> Ba bẫy dữ liệu ở trên: đọc lại và tuân thủ.

---

## Bước 5 — `/tickers` Cổ phiếu

Màn hình hỏng nhất, và là thay đổi cấu trúc lớn nhất của đợt này.

- **Bỏ hẳn bảng 85 dòng đổ dọc.**
- **Vào trang là đã mở sẵn một mã**, mặc định **`VIC`** — điểm neo bước 1, nhóm lớn nhất 19/85.
  Không phải `AAA` (đầu bảng chữ cái, vốn hoá nhỏ), không phải mã thanh khoản cao nhất phiên (đổi
  theo ngày, màn hình mặc định mất ổn định).
- **Ô tìm kiếm luôn ở đó**, kể cả khi đang xem chi tiết. Đổi mã là **một** thao tác. Lọc theo mã,
  tên công ty và ngành, **lọc trong trình duyệt** — 85 dòng đã nằm sẵn trong bộ nhớ, không tốn lời gọi.
- **Hai biểu đồ vẽ lại hoàn toàn.** Đây là màn hình người ta ở lại lâu nhất.
- **Thẻ nhóm điểm neo đang là một câu văn xuôi.** Đây là chỗ duy nhất nối một cổ phiếu với đóng góp
  của đồ án — nó xứng đáng hơn một câu. Dùng `CoverageOrbit` (`as-orbit*`).
- 13 nhận định đang là 13 gạch đầu dòng không phân cấp, mọi câu nặng như nhau.

Bốn chỗ dữ liệu dễ vẽ sai:

- `/history` không truyền mốc → trả **252 phiên gần nhất**. Muốn khoảng khác phải truyền `from`/`to`
  → hàng tab khoảng ở đây là **gọi lại API**, không phải lọc tại chỗ.
- `dist_from_sma_200_pct`, `drawdown_from_252d_high` là **phân số**.
- `latest` có thể **null toàn bộ** trong khi tên mã và phép gán vẫn đầy đủ.
- Câu nhận định **hiển thị nguyên văn**, không cắt, không diễn đạt lại. Quy tắc bị bỏ qua vì thiếu
  đầu vào thì không hiện lý do kỹ thuật; cả 13 quy tắc đều bỏ qua thì nói "chưa đủ lịch sử".

> **Prompt**
> Viết lại `/tickers` theo `reference/ui_kit/TickersScreen.jsx`. Bỏ hoàn toàn `TickerList.tsx`
> dạng bảng 85 dòng. Vào route không có `?t=` thì mở sẵn `VIC`. Ô tìm kiếm (`as-search` +
> `as-count`) luôn hiển thị phía trên phần chi tiết, lọc client-side trên 85 dòng đã nạp một lần
> qua `/api/tickers`; chọn một kết quả chỉ đổi `?t=` và nạp lại 4 lời gọi song song của mã đó.
> Vẽ lại `PriceHistoryChart` và `CombinedIndicatorChart` theo
> `reference/components/charts/PriceVolumeChart.jsx` và `CombinedIndicatorChart.jsx`.
> Thay thẻ nhóm điểm neo văn xuôi bằng `CoverageOrbit`
> (`reference/components/charts/CoverageOrbit.jsx`) — mã đang xem ở tâm hay ở vành tuỳ nó là điểm
> neo hay thành viên. Bốn bẫy dữ liệu ở trên: đọc lại và tuân thủ. Mật độ ở màn hình này **lỏng hơn**
> bảng thị trường — đây là tài liệu, không phải bảng điều khiển.

---

## Bước 6 — `/anchors` Điểm neo

- **Bỏ hẳn 5 mã chưa công bố.** API vẫn trả 15 bước với cờ `in_published_set`; lọc ở phía hiển thị,
  route không đổi.
- **Thêm biểu đồ tỷ trọng** dạng vành khuyên: mỗi điểm neo đại diện bao nhiêu mã trong 85. Đây là
  phân hoạch kín, cộng lại đúng 85, nên biểu đồ tròn là **trung thực ở đây**.
  VIC 19 · PDR 15 · DCM 9 · IDI 8 · CMG 7 · HCM 6 · PVT 6 · VIB 6 · SZC 5 · HSG 4. Nhóm lớn nhất
  gấp gần 5 lần nhóm nhỏ nhất — kết quả đáng chú ý nhất của cả mô hình, hiện chưa được thấy ở đâu.
  Dùng `AnchorShareDonut` (`as-donut*`).
- **Thiết kế lại danh sách điểm neo** — hàng chip + bảng 4 cột đang nói cùng một thứ hai lần.
- **Thành phần ngành là bằng chứng đối chiếu, không phải đầu vào.** Ngành chưa bao giờ đi vào mô
  hình. Trình bày sao cho không ai hiểu nhầm — câu chuẩn: *"Đối chiếu độc lập — ngành không tham
  gia vào việc chọn điểm neo."*
- Chín con số mô hình đang nằm sau một khối gập. Hội đồng sẽ hỏi tới chúng; "gập lại" không phải
  câu trả lời duy nhất.

Ba chỗ dữ liệu dễ vẽ sai:

- `sector_composition` **rỗng `{}` với mọi nhóm** → phải suy ra từ `members[].sector`.
- `F(S) = 22.35` và `Δ` **không phải phân số**, không bị chặn bởi 1 → vẽ chúng thành thanh phần
  trăm là sai. Chỉ `F̄`, `F̄_adj`, `c_i`, `rho2_mean`, `rho2_min` nằm trong [0,1].
- `F̄` và `F̄_adj` **phải hiện cùng nhau**: 0.2629 so với 0.1646; chênh lệch là phần mỗi điểm neo tự
  phủ chính nó. Hiện một mình `F̄` là phóng đại độ phủ khoảng 60%.

> **Prompt**
> Viết lại `/anchors` theo `reference/ui_kit/AnchorsScreen.jsx`. Lọc `in_published_set` để chỉ hiện
> 10 điểm neo, bỏ khối gập "5 mã được chọn tiếp theo". Thêm `AnchorShareDonut`
> (`reference/components/charts/AnchorShareDonut.jsx`) hiển thị phân hoạch 85 mã theo 10 nhóm. Gộp
> hàng chip và bảng 4 cột thành một thứ. Thành phần ngành suy ra từ `members[].sector` (API trả
> `{}`), dùng `CompositionBars`, kèm ghi chú "Đối chiếu độc lập — ngành không tham gia vào việc chọn
> điểm neo." `F̄` và `F̄_adj` luôn cạnh nhau, không bao giờ hiện `F̄` một mình. Không vẽ `F(S)` hay
> `Δ` dưới dạng thanh phần trăm.

---

## Bước 7 — `/about` Giới thiệu

**Không đổi nội dung.** Đây là trang duy nhất có văn xuôi dài trong khi ba trang kia toàn bảng số —
việc cần làm là kéo nó vào cùng một ngôn ngữ thị giác. Dùng `as-prose` cho văn xuôi và
`as-defs`/`as-def-term`/`as-def-value` cho bảng 13 tham số — nơi hội đồng sẽ dừng lại lâu nhất.
Bảng đó là chỗ duy nhất dùng `DD/MM/YYYY` đủ bốn chữ số năm.

> **Prompt**
> Viết lại `/about` theo `reference/ui_kit/AboutScreen.jsx`: `as-prose` cho ba khối chữ,
> `DefinitionList` cho bảng 13 tham số, `formatParamDate` (`DD/MM/YYYY`) cho các mốc ngày trong
> bảng đó. Nội dung chữ giữ nguyên.

---

## Bước 8 — Dọn

1. Xoá mọi rule CSS Module đã chết sau 5 bước trên.
2. `grep` toàn repo tìm mã hex thô và px thô còn sót trong `.module.css` và trong `style={{}}`.
   Còn cái nào là còn nợ.
3. Đối chiếu **6 trạng thái** cho **từng khối** trên cả bốn tuyến — không chỉ mỗi route một lần.
4. Kiểm cả hai mode: `[data-theme="dark"]` và mặc định sáng, cả bốn tuyến.
5. So từng màn hình với `reference/ui_kit/index.html` mở cạnh bên.

> **Prompt**
> Quét `apps/web/src` tìm: (1) mã màu hex hoặc rgb() viết thẳng trong `.module.css`, `.tsx`, hoặc
> `style={{}}`; (2) giá trị px thô ở chỗ đáng ra là token khoảng cách; (3) rule CSS Module không
> còn ai dùng; (4) `font-family` nào khác Roboto / Roboto Mono. Liệt kê theo file kèm token thay
> thế đề xuất, đừng tự sửa trước khi tôi xem.
