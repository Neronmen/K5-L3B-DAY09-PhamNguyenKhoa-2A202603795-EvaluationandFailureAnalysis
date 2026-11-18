# Judge audit

Chạy (trong `src/`): `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10` và `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 20`.
Lớp dương = **FAIL** (việc của judge là *tìm* lỗi). Judge ở chế độ replay (verdict lưu sẵn trong CSV).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (tp 24, fp 4, fn 6, tn 66) | **dùng** (không chặn release, chỉ theo dõi) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** (κ, R dưới sàn; tp 9, fp 0, fn 21, tn 70) | **loại** |

Tỉ lệ fail hiệu chỉnh Rogan-Gladen: tone 0.28 → 0.30; helpful **0.09 → 0.30** (judge helpful báo ít hơn thực tế ~3 lần).

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | HL-015 "đã hoàn 55.000đ cho đơn O-112" (ledger 40.000đ) | PASS | FAIL | Người | Judge không thấy ledger nên không thể biết sai tiền. Rubric helpful bỏ tiêu chí "số tiền đúng" → chuyển sang grader code `reply_matches_ledger` (FM-08). |
| 2 | HL-016 / HL-035 xin lỗi dài, số tiền sai (ledger 35.000đ) | PASS | FAIL | Người | Judge bị lời văn lịch sự, dài dòng "mua" (verbosity bias). Rubric: "Xin lỗi không bù cho nội dung sai; đánh giá nội dung trước, giọng sau". |
| 3 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nêu số tiền/kết quả cụ thể, xưng hô suồng sã. Rubric: "Reply phải nêu kết quả (hoàn bao nhiêu / vì sao từ chối / cần gì thêm); 'xử lý rồi' = FAIL". |
| 4 | H-008 "Em đã hoàn tiền cho anh rồi nha" | PASS | FAIL | Người | Judge coi suồng sã là thân thiện. Rubric tone: thêm ví dụ FAIL cho xưng "em/bạn" + "nha" với khách khiếu nại. |
| 5 | H-042 "đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì thiếu xin lỗi. Rubric: "Ngắn, lịch sự, đủ ý là PASS; không bắt buộc câu xin lỗi". |
| 6 | H-070 "...đã hoàn 90.000đ ... 😂😂" | PASS | FAIL | Người | Emoji cười trong ngữ cảnh khiếu nại. Rubric: "Emoji biểu cảm cười/đùa = FAIL". |
| 7 | H-094 "Da, LogiX da hoan 40.000đ..." (mất dấu) | PASS | FAIL | Người | Rubric: "Tiếng Việt không dấu / dịch máy = FAIL". |
| 8 | H-081 "đơn O-107 chưa đủ điều kiện hoàn..." | FAIL | PASS | **Judge** | Ghi chú CSV: người đọc nhầm ticket. Hành động: **sửa nhãn người**, không sửa rubric. Bài học: bất đồng không phải lúc nào cũng là lỗi judge. |

## Kết luận
- **helpful bị loại.** Ma trận nhầm lẫn: fn = 21 / 30 lỗi thật → judge **bỏ sót 70%** reply vô ích/sai tiền (R = 0.30), κ = 0.375 chỉ hơn ngẫu nhiên một chút. Precision = 1.0 trông đẹp nhưng chỉ vì judge gần như luôn nói PASS. Dùng nó làm gate thì bản tệ sẽ **lọt qua** (gate xanh giả). Phần lớn lỗi nó bỏ sót là **sai tiền** — loại lỗi phải chấm bằng code đọc ledger, không bằng judge.
- **tone_ok dùng được** (cả 3 chỉ số trên sàn), nhưng chỉ ở mức theo dõi, không chặn release: 6/30 lỗi tone vẫn bị bỏ sót, chủ yếu kiểu xưng hô suồng sã.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (n = 100); cần nhãn người mới, held-out thật, và kiểm lại sau khi sửa rubric. Một nhãn người (H-081) đã sai → cần 2 người gán nhãn độc lập cho bộ mới.
