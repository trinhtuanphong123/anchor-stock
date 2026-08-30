# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.


# Anchor Stock — luật design system

Append phần này vào `CLAUDE.md` ở gốc repo. Nó là thứ giữ cho lần refactor thứ mười vẫn giống lần
thứ nhất.

## Nguồn chân lý

Token và class ở `apps/web/src/styles/ds/`. Một component **chỉ được viết `var(--*)`** — không một
mã màu, không một cỡ chữ, không một khoảng cách viết thẳng. Chính chỗ gián tiếp đó là lý do lần đổi
bảng màu trước chỉ là sửa vài dòng khai báo thay vì viết lại từng thành phần.

CSS Modules vẫn dùng, nhưng chỉ cho layout cục bộ (grid, tỷ lệ cột, vị trí). Hình thức — màu, chữ,
viền, bo góc, hover, focus — thuộc lớp `as-*` toàn cục.

## Luật màu

- **Xanh tăng / đỏ giảm.** Màu trên một con số nghĩa là **chiều biến động giá và không gì khác.**
  Vì vậy huy hiệu trạng thái là teal / hổ phách / xanh dương, và thanh thành phần ngành là accent.
- **Mỗi chiều có hai bậc.** `--data-pos` / `--data-neg` cho **chữ**; `--data-pos-mark` /
  `--data-neg-mark` cho **nét vẽ, vùng tô, ô treemap**. Lý do: `#089981` đo 3.57:1 trên nền trắng —
  đạt cho nét 1.5px, **trượt AA cho chữ 13px**, mà 13px là cỡ bảng biến động đặt màu đó lên ở gần
  như mọi dòng. **Đặt token `-mark` lên chữ là một bug.**
- `null` không bao giờ được vẽ bằng màu của `0%`. Trung tính là `--data-neutral`.

## Luật chữ

Roboto cho chữ, Roboto Mono cho **mọi con số**, chỉ **400 và 500**. Không có 600/700 nào được nạp,
nên phân cấp do **cỡ và màu** gánh — muốn thêm trọng lượng phải nạp thêm và phải nói rõ.

Mọi cột số: `tabular-nums`, **căn phải**. Một cột giá xê dịch một pixel khi chữ số đổi là cách rõ
nhất để một bảng đọc ra dáng tay ngang.

## Luật viết chữ hiển thị

- **Tiếng Việt toàn bộ.** Ngoại lệ: tên thương hiệu, mã cổ phiếu, và ký hiệu không có bản dịch
  (`RSI`, `MACD`, `F̄`, `ρ²`, `τ`, `Δ`, `SMA`, `YTD`).
- **Ngôi thứ ba về dữ liệu.** Không "tôi", không "bạn": *"Mã này được đại diện bởi VIC"*, không
  *"Cổ phiếu bạn chọn…"*. Không có giọng onboarding, không lời chào, không động viên.
- **Không bao giờ tư vấn.** Hệ thống không dự báo, không khuyến nghị, không tính xác suất, không đề
  xuất tỷ trọng. Không "nên mua", không "tiềm năng", không "cảnh báo rủi ro".
- **Câu phòng ngừa hiểu sai là nội dung, không phải chú thích để cắt.** Ví dụ: *"Mỗi điểm là một
  phiên, không phải một thời điểm trong phiên."* · *"Ô trống là 'chưa tính được', không phải 0%."* ·
  *"Đối chiếu độc lập — ngành không tham gia vào việc chọn điểm neo."*
- **Sentence case** ở mọi văn xuôi và tiêu đề. CHỮ HOA chỉ dành cho nhãn micro 11px và do **CSS**
  làm, không bao giờ gõ tay.
- **Nhãn có chữ Hy Lạp không bao giờ uppercase** — `text-transform: uppercase` biến τ thành Τ, đọc
  ra chữ T Latin. Đó là lý do `.as-def-term` và nhãn `.as-provenance` bỏ transform.
- **Đơn vị luôn gọi tên tại chỗ hiển thị.** "GT giao dịch (tỷ đ)", "Giá đóng cửa (nghìn đ)",
  "18.42 nghìn tỷ đ". Hai đơn vị tiền cùng tồn tại có chủ ý.

## Luật ký tự

Không emoji. Ở đâu cũng không. Ngoài chữ và số, chỉ có sáu glyph được dùng:

| Glyph | Dùng ở |
|---|---|
| `—` U+2014 | Mọi giá trị thiếu, mọi nơi. **Không bao giờ `0`** |
| `·` U+00B7 | Dấu phân cách trong dải provenance và ghi chú |
| `▸` U+25B8 | Mũi khối gập, quay 90° khi mở |
| `⚠` U+26A0 | Cạnh mã có `bar_date` cũ hơn phiên |
| `→` `←` | Liên kết chuyển màn hình |
| `τ ρ² Δ F̄` | Ký hiệu mô hình |

**Không có bộ icon, và thêm một bộ là phát minh.** Không icon font, không SVG sprite, không Lucide,
không Heroicons. Thứ ở sản phẩm khác là icon thì ở đây là **một từ**: "Nền tối", "Tăng", "Giảm",
"Điểm neo", "độ phủ thấp". Trạng thái sắp xếp bảng do cột được nhấn mạnh và thanh trong ô gánh,
không phải mũi tên. Nếu một màn hình mới thật sự cần icon: **nêu ra như một quyết định thiết kế**,
đừng lặng lẽ thêm thư viện.

## Luật bề mặt

Một card là viền 1px `--border-subtle` trên `--surface-card`, bo `--radius-card` (6px), nằm trên
canvas hơi ngả màu. **Card không nổi.** Cả sản phẩm dùng đúng một bậc của thang shadow:
`--shadow-md` cho tooltip biểu đồ, thứ duy nhất thật sự chồng lên nội dung khác. **Không viền lồng
viền** — treemap trong panel thì bỏ viền của chính nó.

Nền là **màu phẳng**. Không ảnh, không hình vẽ, không ảnh chụp, không gradient trang trí, không
texture, không pattern. Gradient duy nhất trong cả hệ là vùng tô của biểu đồ. **Không blur ở bất cứ
đâu** — không header mờ, không scrim.

Bo góc: 2 / 4 / 6 / 8 / 999. Control 4, card 6, badge và chip pill. Không gì tròn hơn 8px trừ pill —
một bảng số được làm từ hình chữ nhật.

**Không có logo hình.** Thương hiệu là chữ "Anchor Stock" đặt bằng Roboto Medium. **Đừng vẽ một
mark.** Sản phẩm không có ảnh nào, và đừng phát minh ảnh.

## Luật chuyển động

Chỉ chuyển màu và nền, **100ms** (`--duration-fast`) trên `--ease-out`. **Không gì dịch chuyển, phóng
to, nảy hay trượt.** Cả hệ có đúng hai keyframe: skeleton nhấp nháy (1.5s opacity) và spinner
(0.75s). Một bảng mà các dòng di chuyển là một bảng người đọc mất dấu.

Hover: **tint nền**, không nâng lên, và **không đổi màu của dữ liệu**. Press: không co, không shadow.
Focus: outline 2px `--accent`, offset 2px, ở mọi nơi, không biến tấu.

## Luật biểu đồ

SVG viết tay, **không thư viện**. `viewBox` cố định, scale bằng CSS, `vector-effect:
non-scaling-stroke` để nét 1.5px vẫn là 1.5px trên màn rộng. **Thang giá bên phải**, vì thanh mới
nhất ở đó. Gridline rơi vào bước "đẹp". Vùng tô đóng về **mức mở cửa của khoảng** — có baseline nét
đứt màu hổ phách — chứ không đóng về khung, vì thứ nó tô là phần tăng trong khoảng. Chip giá cuối
ghim vào thang. Crosshair là nét đứt trung tính, **không bao giờ tô màu**, và chạy được **cả bằng bàn
phím**. Treemap là ngoại lệ duy nhất của viewBox cố định: nó đo hộp pixel thật.

## Luật bố cục

Header hai tầng, dính cả cụm; **thanh tab là thứ duy nhất nói route hiện tại**. Vùng nội dung căn
giữa, gutter 24px, tối đa 1440px. **Mỗi khối tự gọi API của mình và tự hiển thị trạng thái của
mình** — một khối chậm không được làm trắng khối đã xong, và bố cục không được ép một khối chờ khối
khác.

Hai mật độ, có chủ ý: bảng thị trường chạy dòng 32px, đầu cột 11px giãn chữ, phân cách bằng hairline;
`/tickers` và `/anchors` là **tài liệu** và chạy lỏng hơn. Hai bên dùng chung lớp token và **bất
đồng về mật độ một cách cố ý** — đừng "thống nhất" chúng.

## Ba bẫy số học, tuân thủ ở mọi nơi

1. `dist_from_sma_200_pct` và `drawdown_from_252d_high` là **phân số** dù tên nghe như phần trăm.
   `0.05` là `+5%`. Đừng nhân hai lần.
2. `F(S) = 22.35` và `Δ` **không phải phân số**, không bị chặn bởi 1 → không vẽ thành thanh phần
   trăm. Chỉ `F̄`, `F̄_adj`, `c_i`, `rho2_mean`, `rho2_min` nằm trong [0,1].
3. `F̄` và `F̄_adj` **luôn hiện cùng nhau** (0.2629 vs 0.1646). Hiện một mình `F̄` là phóng đại độ
   phủ khoảng 60%.

Và: tăng/đứng/giảm chỉ tính trên mã **có** `ret_1d`, không cộng lại thành 85. `sector_composition`
trả `{}` với mọi nhóm — suy từ `members[].sector`. Chuỗi chỉ số một điểm là một phiên → **không có
khoảng "1D"**.

## Ràng buộc không được vi phạm

- Đúng **bốn tuyến**: `/`, `/tickers`, `/anchors`, `/about`. Không thêm trang. Không trang giới
  thiệu kiểu tiếp thị, không chân trang nhiều cột.
- **Chỉ desktop** đợt này. Tối đa 1440px.
- **Không một thao tác ghi nào** tồn tại trên sản phẩm. Không form, không dialog, không toast, không
  button gọi hành động. DS **không cung cấp** Button, Input, Select, Checkbox, Radio, Switch, Tabs,
  Dialog, Toast, Tooltip, Avatar — và đó là chủ ý, không phải thiếu sót.
- Xuất tĩnh: không SSR, không route động. Trang chi tiết dùng query string (`?t=VCB`, `?a=VIC`).
- Sáng mặc định, tối qua `[data-theme="dark"]`, **cả hai hoàn chỉnh như nhau**.
- Bản deploy **không bao giờ** dựng dữ liệu giả. Thiếu cấu hình là hiện lỗi, không phải hiện số bịa.

## Vibe

Một bảng giao dịch đã đọc phương pháp luận của chính nó và từ chối nói quá về nó.
