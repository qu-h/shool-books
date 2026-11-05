# Push dữ liệu theo đợt tối đa 1 GB

`push_data_batches.py` chỉ thêm các file mới/thay đổi trong `data/`; giữ nguyên các file mã nguồn ngoài phạm vi này và từ chối chạy nếu index đang có thay đổi được stage sẵn. Script dùng cùng khóa với bộ tải sách để dữ liệu không thay đổi trong lúc chia đợt.

Mức trần là **1.000.000.000 byte**, không phải 1 GiB. Mỗi đợt chọn tối đa khoảng 950 MB file, dành phần còn lại cho object/tree/commit của Git và lịch sử chưa push. File nguyên vẹn nên không thể đảm bảo đúng tròn 1 GB mỗi lần; đợt cuối thường nhỏ hơn.

Trước mỗi commit, script kiểm tra chính xác danh sách và số byte của blob trong index. Trước mỗi push, script tạo luồng pack vào bộ đếm, không ghi thêm bản pack 1 GB ra ổ, và từ chối push nếu pack vượt trần. Push dùng cùng cấu hình nén, tắt tìm delta mới và dùng `--no-thin` để gửi đủ dữ liệu nền cần giải mã các object trong gói. Việc đếm pack cũng không dùng thin pack; đồng thời tắt sparse traversal khi chọn object. Giới hạn áp dụng cho payload pack Git; phần giao thức SSH/TCP không nằm trong phép tính này.

Mỗi đợt thực hiện theo thứ tự add → commit → đo pack → push → xác nhận remote. Chỉ chuyển sang đợt tiếp theo sau khi nhánh remote trỏ đúng commit vừa gửi. Không force push, không gộp nhiều đợt chưa gửi vào lần push tiếp theo. Khi một lần push thất bại, chạy lại sẽ kiểm tra và gửi commit còn chờ trước khi thêm dữ liệu mới nếu cần.

Xem kế hoạch, không thay đổi Git:

```sh
python3 scripts/push_data_batches.py
```

Thực hiện khi đã xác nhận remote/nhánh đích:

```sh
python3 scripts/push_data_batches.py --execute
```

Đích mặc định là remote `origin`, nhánh hiện được checkout. Script dừng nếu remote có lịch sử phân kỳ hoặc thay đổi trong khi chạy. Các thao tác add/commit không bao gồm chính script này hay các file hướng dẫn ngoài `data/`.

Nhật ký từng lần push nằm tại `.git/data-push-batches.jsonl`, ghi commit, số file, byte đã add, byte pack và mức trần. Script kiểm tra dung lượng trống trước mỗi đợt và chỉ tối ưu object Git sau push khi có đủ chỗ cho cả dữ liệu tạm; không xóa file sách để giải phóng chỗ.

Kế hoạch tại thời điểm chuẩn bị:

| Đợt | File mới | Byte add |
| --- | ---: | ---: |
| 1 | 1.743 | 939.995.895 |
| 2 | 1.481 | 949.907.471 |
| 3 | 1.260 | 949.855.418 |
| 4 | 1.521 | 949.838.007 |
| 5 | 1.258 | 173.711.886 |

Đợt đầu còn bao gồm lịch sử chưa push có 9.953.262 byte object gốc. Kế hoạch sẽ được tính lại theo trạng thái thật trước khi thực hiện; kích thước pack được đo sau từng commit. Bộ tải được tạm dừng để dành dung lượng cho object Git. Toàn bộ sách còn lại vẫn cần thêm chỗ lưu trước khi có thể tải xong.

## Khi GitHub báo `pack has unresolved deltas`

Kiểm tra `git fsck --full --no-dangling` và xác nhận commit nào còn ở local. Để gửi lại đúng commit hiện tại, có thể dùng push không tạo thin pack, không tạo delta mới và tắt automatic maintenance trong lần chạy đó:

```sh
git -c gc.auto=0 -c maintenance.auto=false -c pack.window=0 -c pack.useSparse=false push --no-thin origin HEAD:refs/heads/main
```

Không add hoặc commit thêm dữ liệu khi đợt hiện tại chưa push thành công. Không cần reset, amend hoặc force push. Nếu ổ đầy và Git báo `tmp_pack_*` là garbage, chỉ di chuyển file tạm khi đã xác nhận không có tiến trình dùng nó; không xóa pack/object thật.
