# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@11` (item E-014), run ID `E-seeded_regression-20261118-c44d`, eval set `c44d6317c5c2` |
| Triệu chứng | `pass_rate` FAIL (`proposal_mismatch`), `refund_amount_correct` FAIL (ledger 90.000 ≠ nhãn 120.000), `reply_matches_ledger` FAIL (reply "đã hoàn 120.000đ" nhưng ledger 90.000), `quote_kept` FAIL. Khách bị trừ tiền đã hoàn **hai lần**, còn reply thì nói số đúng-trên-giấy → nhìn reply không thấy lỗi. |
| Bước sai đầu tiên | **Event 5 `proposal {"amount_vnd": 120000}`** — agent tự trừ `refunded_vnd 30000` (đọc ở event 4 `refund_history`) khỏi quote chính thức 150.000 trước khi gọi host. |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` và 2 `investigator` đúng (đơn O-515 visible, delay theo DB, không có `model_override`); event 3 `quote` = 150.000 (SHIP-LATE-03 + DMG-04, lấy max) đúng như `compute_compensation`; event 4 `refund_history` chỉ là đọc (read-only), đúng dữ liệu. Event 5 là chỗ đầu tiên agent **thay đổi** con số chính thức. |
| Failure mode | **FM-05 pre_deducted** (hệ quả kéo theo FM-08: reply ≠ ledger) |
| Đối chứng | `fixed C-014@11`: event 3 `quote 150000` → event 4 `reply` "đã hoàn 120.000đ" — **không có** `refund_history`/`proposal`; host `issue_refund` tự trừ 30.000 một lần, ledger 120.000 = nhãn. |
| Regression test | `src/tests/test_lab9_trace_case.py::test_lab9_c014_pre_deducted_caught_and_fixed_passes`: chạy cả hai shape, assert `RefundAmountCorrect`, `ReplyMatchesLedger`, `QuoteKept` FAIL trên `seeded_regression` và PASS trên `fixed`, và `refund_history` đứng trước `proposal`. Đã chạy: 1 passed. |
| Chưa chắc chắn | Trace không cho biết agent trừ vì "hiểu nhầm" hợp đồng của host hay vì prompt; MockLLM tất định nên không biết lỗi có lặp với LLM thật ở cùng tần suất không. Trace cũng không ghi số host đã trừ (chỉ thấy qua ledger). |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
