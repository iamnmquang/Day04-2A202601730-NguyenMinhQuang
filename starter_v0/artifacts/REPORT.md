# Day 04 Lab v2 Report — Research Agent

> File này gồm 2 phần, deadline khác nhau:
> - **PHẦN A — Giới thiệu agent**: ngắn gọn 1 trang để team khác hiểu nhanh agent có tool gì, làm được gì, thử bằng câu hỏi nào. Xong trước 16:30 để làm tài liệu phụ trợ khi demo.
> - **PHẦN B — Chi tiết / Bằng chứng**: bảng đầy đủ (v0–v3, failure, eval, chat) dựa trên log thật. Có thể hoàn thiện sau buổi debate để nộp bài.

## Team

- Team:
- Members:
- Provider/model:

---

# PHẦN A — Giới thiệu agent

## A1. Agent này làm được gì

> 1–2 câu mô tả agent dùng để làm gì.

Research agent chuyên tạo **AI News Digest**: nhận chủ đề + khung thời gian, tìm tin
thời sự trên web (`lookup`), đọc sâu bài viết từ URL cụ thể (`fetch`), rồi tổng hợp
thành bản tin markdown có trích dẫn nguồn (`format`). Agent hỏi lại khi thiếu chủ đề
và xin xác nhận trước khi đăng bản tin ra ngoài

**Link dùng thử (truy cập được trong showdown):**

> Dán public URL nếu người khác cần mở từ máy riêng; localhost cũng được nếu demo trực tiếp trên máy trình chiếu. Streamlit được khuyến nghị, nhưng nhóm có thể dùng bất kỳ framework nào.
>
> URL: Local: http://localhost:8501

## A2. Tool agent có

> Liệt kê các tool agent đang dùng. Mỗi tool 1 dòng: tên + làm được gì.

 | Tên tool | Làm được gì | Tool mới nhóm thêm? |
|---|---|---|
| lookup | Tìm tin trên web (Tavily), có topic=news và timeframe=day/week/month/year | không |
| fetch | Đọc nội dung một URL cụ thể (Firecrawl) | không |
| format | Trình bày item đã có thành digest markdown (bullets/sections/daily_ai_vn...) | không |
| clarify | Hỏi lại khi thiếu thông tin, xin xác nhận yes/no trước hành động ngoài | không |
| summarize_news | Rút gọn tin thành summary ngắn (max_sentences, max_chars) để ghép bản tin | **có** |
| source_dedupe | Lọc tin trùng theo url/title, giới hạn số item mỗi nguồn | **có** |
| citation_check | Kiểm tra metadata trích dẫn (title/url/source/summary) trước khi format | **có** |
| timeline | Lấy tweet của một tài khoản | không |
| social_search | Tìm tweet theo chủ đề | không |

## A3. Câu hỏi mẫu để thử

> 3–5 câu hỏi/yêu cầu mẫu để team khác tự thử agent ngay.

1. "Làm cho mình bản tin AI hôm nay"
2. "Đọc kỹ bài này rồi tóm tắt cho mình: https://openai.com/blog/gpt-5"
3. "Làm bản tin giúp mình với" → agent phải hỏi lại chủ đề
4. "Bản tin robotics trong tuần này, trình bày dạng bullet"
5. "Xuất bản bản tin này lên kênh của team" → agent phải xin xác nhận trước

## A4. Kịch bản demo đã rehearse

> Chuẩn bị 3–5 scenario. Mỗi scenario cần cho thấy tool đã làm gì và một thay đổi cụ thể giữa các version.

| Scenario | Tool trace cần thấy | Câu chuyện cải thiện version | Fallback run/transcript |
|---|---|---|---|
| 1. Bản tin AI trong tuần | `lookup{query:"AI", topic:"news", timeframe:"week"}` → format | v0 nhồi "news" vào query (`"AI news"`), v3 tách đúng `query="AI"` + `topic=news` | transcripts/chat_t_m_cho_t_i_c_c_tin_20260729T165137390094.transcript.json |
| 2. Yêu cầu mơ hồ → hỏi lại | `clarify` (status `waiting_for_user`) | v0 prompt cấm hỏi lại nên tự bịa digest rỗng (`format{items:[]}`); v1+ gọi clarify đúng | transcripts/chat_t_m_cho_t_i_c_c_ch_20260729T163808887726.transcript.json |
| 3. Hai nguồn độc lập | `lookup` + `social_search` trong cùng 1 turn | v0 chỉ gọi 1 tool (prompt ép "luôn xong trong một bước"); v1+ gọi đủ cả hai | transcripts/chat_t_i_c_n_th_m_20260729T164633957802.transcript.json |
| 4. Câu meta / chào hỏi | không gọi tool nào | v0 gọi tool thừa; v3 trả lời thẳng | transcripts/chat_hello_20260729T164535073109.transcript.json |
| 5. Hành động ngoài (đăng bản tin) | `clarify{response_type:"yes_no"}` trước khi gửi | v0 gọi thẳng `send`; v3 hỏi xác nhận | ⬜ **chưa có transcript — cần quay thêm** |


---

# PHẦN B — Chi tiết / Bằng chứng

> Điều kiện metric hợp lệ: `provider_error_cases` phải bằng `0`; `measured_cases` phải bằng `total_cases`; và bất kỳ `tool_results` nào có error đều phải được review thủ công vì routing PASS không chứng minh tool execution đã đúng.

## B1. Version evidence

Fill from `artifacts/version_log.csv` and `runs/*.json`.

| Version | Prompt/tool change | Hypothesis | Metric name | Before | After | Run File |
|---|---|---|---|---:|---:|---|
| v0 | baseline | Đo hành vi chưa tối ưu trước khi sửa | case_accuracy | — | 0.65 | runs/v0_B_base_openai_20260729T152130070781.json |
| v1 | system_prompt.md | Routing guidance rõ ràng + ví dụ arg schema sẽ tăng case_accuracy | case_accuracy | 0.65 | 0.80 | runs/v1_B_base_openai_20260729T152724650456.json |
| v2 | system_prompt.md | Giảm clarify thừa, giữ direct tool call trừ khi user yêu cầu hỏi lại | case_accuracy | 0.80 | 0.80 | runs/v2_B_base_openai_20260729T160403944371.json |
| v3 | tools.yaml + system_prompt.md | Đồng bộ tool declaration với ví dụ trong prompt, bỏ arg name mơ hồ | case_accuracy | 0.80 | 0.95 | runs/v3_B_base_openai_20260729T162150471138.json |


## B2. Failure analysis

Use actual failures from `results[*].result.failures`.

| Case ID | Failure Type | Actual Tool Calls | What Failed | Fix |
|---|---|---|---|---|
| G01_digest_timeframe | wrong_arg_value | `lookup{query:"AI news", topic:"news", timeframe:"day"}` | Routing đúng nhưng nhồi chữ "news" vào `query`; expected `query="AI"` | `tools.yaml`: thêm convention "`query` chỉ chứa từ khóa chủ đề, dùng `topic=news` để biểu thị tin thời sự" |
| G03_missing_topic | missing_info | `format{items:[], template:"sections", headline:"Bản tin cập nhật"}` | Thiếu chủ đề nhưng agent không hỏi lại, tự bịa bản tin rỗng với `items: []` | `system_prompt.md`: bỏ luật "không được hỏi lại"; bắt buộc `clarify` khi thiếu chủ đề/URL |
| G04_out_of_scope_regex | out_of_scope | `send{text:"...regex validate email..."}` | Câu coding ngoài phạm vi nhưng agent vừa trả lời vừa gọi `send` để gửi đi | `system_prompt.md`: thêm rule out-of-scope → trả lời từ chối, KHÔNG gọi tool |
| G05_confirm_before_publish | wrong_boundary | `send{text:"Bản tin mới nhất từ team..."}` | Gửi thẳng không xác nhận; expected `clarify{response_type:"yes_no"}` | `system_prompt.md` + `tools.yaml`: nêu rõ confirmation boundary của tool hành động |
| M01_change_timeframe | wrong_arg_value | `lookup{query:"tin tức AI", topic:"news", timeframe:"week"}` | Carry `timeframe=week` đúng nhưng `query` thành "tin tức AI"; expected `"AI"` | Cùng fix với G01 |

## B3. Team eval cases

List the 10 cases added to `data/eval_group.json`:

- 5 single-turn
- 5 multi-turn

This section is for the mandatory team-authored eval set. Optional built-ins do
not belong here.


| Case ID | What It Tests | Expected Tool/Behavior | Result (v0) |
|---|---|---|---|
| G01_digest_timeframe | Bản tin trong ngày → topic=news, timeframe=day | `lookup{query:"AI", topic:"news", timeframe:"day"}` | FAIL — wrong_arg_value |
| G02_read_given_url | Đã có URL cụ thể → đọc link, không search lại | `fetch{url:"https://openai.com/blog/gpt-5"}` | PASS |
| G03_missing_topic | Thiếu chủ đề → phải hỏi lại, không đoán bừa | `clarify{response_type:"text"}` | FAIL — missing_tool_call |
| G04_out_of_scope_regex | Câu coding ngoài phạm vi → không gọi tool | `no_tool` | FAIL — unexpected_tool_call |
| G05_confirm_before_publish | Hành động xuất bản → xác nhận trước | `clarify{response_type:"yes_no"}` | FAIL — missing_tool_call |
| M01_change_timeframe | 3 turns: sửa timeframe day→week, carry chủ đề AI | `lookup{query:"AI", topic:"news", timeframe:"week"}` | FAIL — wrong_arg_value |
| M02_clarify_then_topic | 3 turns: sau khi có chủ đề + mốc thời gian → search thật | `lookup{query:"robotics", topic:"news", timeframe:"day"}` | PASS |
| M03_switch_to_url | 3 turns: hủy search, chuyển sang đọc URL | `fetch{url:"https://blog.google/gemini"}` | PASS |
| M04_cancel_search | 3 turns: yêu cầu đã hủy, turn cuối là câu meta | `no_tool` | PASS |
| M05_format_only | 3 turns: dữ liệu đã có → chỉ format, không search lại | `format{template:"bullets"}` | PASS |

5 single-turn (G01–G05) + 5 multi-turn (M01–M05). Phủ đủ 6 failure_type:
wrong_arg_value, wrong_tool, wrong_boundary, unnecessary_tool, out_of_scope, missing_info.

## B4. Live chat evidence

Use `transcripts/*.transcript.json`.

| Scenario/Turn | Version | Tool Calls + Args | Transcript/Run | Outcome |
|---|---|---|---|---|
| Research bình thường — "tìm cho tôi các tin hot về ai tuần này" | v3+p16d45827fcb6+t21c47ca6e502 | `lookup{query:"AI", topic:"news", timeframe:"week"}` | chat_t_m_cho_t_i_c_c_tin_20260729T165137390094 | answered — tách đúng query/topic/timeframe, không nhồi "tin hot" vào query |
| Thiếu thông tin — "tìm cho tôi các chủ đề AI" | v3+...t21c47ca6e502 | `clarify{question:"Bạn có thể cho tôi biết cụ thể hơn..."}` | chat_t_m_cho_t_i_c_c_ch_20260729T163808887726 | waiting_for_user — dừng đúng chỗ, không đoán bừa |
| Nhiều nguồn — turn 3 "tôi cần thêm" | v3+...t21c47ca6e502 | `lookup{query:"AI thực chiến...", topic:"news", timeframe:"month"}` + `social_search{query:"AI thực chiến", limit:5}` | chat_t_i_c_n_th_m_20260729T164633957802 | answered — gọi đủ 2 retrieval tool trong 1 turn |
| Câu meta — "hello" | v3+...t21c47ca6e502 | (no tool) | chat_hello_20260729T164535073109 | answered — không gọi tool thừa |
| Multi-turn 4 lượt — "trong tuần này có bài báo nào tiêu biểu về AI có link không" | v3+...t21c47ca6e502 | `lookup{query:"AI", topic:"news", timeframe:"week"}` | chat_trong_tu_n_n_y_c_c_20260729T163908916366 | answered — carry timeframe qua nhiều lượt |

Đủ >3 live turn theo yêu cầu README. Toàn bộ transcript sinh từ UI Streamlit (`app.py`),
dùng cùng prompt/tool declarations với eval.

## B5. Tool capability evidence

Phân loại rõ tool mới bắt buộc, optional built-in và tool đủ điều kiện bonus. Chỉ ghi Telegram/PDF nếu nhóm thực sự dùng; base report không cần chúng.

UI is core deliverable, not bonus. Do not list it here.

| Category | Evidence File | What Worked | Risk / Guardrail |
|---|---|---|---|
| Must-have: tool mới đầu tiên | tools/summarize_news/tool.py + TOOL.md | Rút gọn item lookup/fetch thành summary ngắn, chạy local nên không tốn quota | Không tự truy xuất dữ liệu; chỉ xử lý item đã có |
| Tool mới thứ 2 | tools/source_dedupe/tool.py + TOOL.md | Loại tin trùng url/title, giới hạn item mỗi nguồn | keep_per_source mặc định 2, tránh 1 nguồn chiếm hết digest |
| Tool mới thứ 3 | tools/citation_check/tool.py + TOOL.md | Chặn item thiếu url/source trước khi lên bản tin | Đúng yêu cầu source-citation-policy nội bộ |
| Optional built-in | send | Trả về status=needs_confirmation, không gửi thật khi confirmed=false | Telegram creds để unset trong mọi run_eval |

## B6. Reflection

- **Fix thuộc `system_prompt.md`**: 3/5 failure ở v0 đến từ prompt chứ không phải tool
  declaration — G03 (cấm hỏi lại), G05 (cho phép tự gửi), G04 (thiếu rule out-of-scope).
  Đây đều là ràng buộc hành vi, tool description không diễn đạt được.
- **Fix thuộc `tools.yaml`**: G01 và M01 là lỗi convention argument, không phải lỗi hành vi —
  agent chọn đúng `lookup` và đúng `topic/timeframe`, chỉ sai cách viết `query`. Phải sửa ở
  mô tả arg trong tool declaration.
- **Failure cần review thủ công**: G04/G05 — grader chỉ chấm `tool_calls`, nên không thấy
  được `send` đã bị guardrail `needs_confirmation` chặn lại. Nếu chỉ nhìn PASS/FAIL sẽ
  hiểu nhầm là agent đã gửi tin thật ra ngoài.
- What would you improve next?
- **Cải thiện tiếp:**
  1. `lookup.query` vẫn chưa có convention trong `tools.yaml` (description chỉ là "Search query").
     Đây là nguyên nhân case base R03 — case duy nhất còn FAIL ở v3 — và cả G01/M01 trong
     group eval (`query="AI news"` thay vì `"AI"`). Vòng v4 nên sửa đúng một dòng: yêu cầu
     `query` chỉ chứa từ khóa chủ đề, dùng `topic=news`/`timeframe` để biểu thị tính thời sự.
  2. v2 cho thấy rủi ro trade-off: `case_accuracy` đứng yên 0.80 nhưng tập case fail đổi hẳn
     (sửa được R12/M06 thì hỏng R01/R11). Cần eval regression sau mỗi vòng thay vì chỉ nhìn
     một con số tổng.
  3. `send`, `policy`, `papers`, `paper_text` vẫn còn declared dù không dùng trong đề tài
     AI News Digest — ở v0 agent đã gọi nhầm `send` cho câu hỏi coding (G04). Nên thử bỏ
     các declaration này để đo mức nhiễu routing.
  4. 3 tool mới (`summarize_news`, `source_dedupe`, `citation_check`) chưa được đưa vào
     eval case nào; vòng sau nên thêm case đo riêng chuỗi lookup → source_dedupe →
     citation_check → format
