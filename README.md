# M28 Landmark Studio · bản demo công khai

Bản chạy trên mạng của **tool thật** M28 Landmark Studio (đội T015-SIXSEVEN, P-015): trang rà soát Gradio với đợt mẫu 10 mặt đã qua MediaPipe.
Mã nguồn đầy đủ của tool (kiến trúc, đặc tả, kiểm thử) nằm ở repo của đội; bản demo này gồm mã tool đã vá (`tool/`, `patch_demo.py`).

## Khác với bản chạy trên máy người gán nhãn
- Bật bằng biến môi trường `M28_PUBLIC_DEMO=1`: mở cho mọi Host và lắng nghe `0.0.0.0` (bản thật chỉ nhận `127.0.0.1` để ảnh mặt không rời máy).
- Không đóng được trang, không nạp ảnh mới, nút "Open CVAT task" bị khoá.
- Tự đặt lại đợt mẫu khi có người thao tác rồi im lặng 5 phút (`demo_main.py`).
- Phần còn lại là mã tool gốc (`tool/`), chỉ vá bằng `patch_demo.py` + `demo_block.py` (đọc để biết đã vá gì).

## Hai chế độ CVAT (tự chọn theo biến môi trường)
| Chế độ | Khi nào | Cách hoạt động |
|---|---|---|
| **CVAT thật** | Có `CVAT_ACCESS_TOKEN` (và `CVAT_URL`, mặc định `https://app.cvat.ai`) | Tool đẩy và thu nhãn trên CVAT đó bằng `cvat-sdk` 2.79.0, trong project riêng (`M28_DEMO_CVAT_PROJECT`, mặc định `m28-demo`). Người xem không sửa được trên CVAT, nên một luồng nền "người gán mô phỏng" tự đánh dấu job Xong vài giây sau khi tạo task và xoá task demo cũ (`Lam-NAP_*`). **Dùng một tài khoản CVAT riêng cho demo**, không dùng tài khoản chính. |
| **Mô phỏng** | Không có token, hoặc `M28_DEMO_CVAT=fake` | Gói `cvat_sdk` giả (`fake_cvat/`) nằm ngay trong tiến trình; job tự chuyển Mới → Đang sửa → Xong theo thời gian. Địa chỉ `https://cvat.mo-phong.demo` là tên giả: **không có kết nối mạng tới CVAT nào**, kể cả CVAT trên máy người xem. |

Banner ở góc dưới trang nói rõ đang ở chế độ nào. Phiên bản CVAT của chế độ thật mặc định là 2.79 (`M28_DEMO_CVAT_VERSION`); repo chính của tool vẫn nhận CVAT 2.77 và 2.78.

## Chạy thử
```bash
docker build -t m28-demo . && docker run --rm -e PORT=8000 -p 8000:8000 m28-demo
# mở http://localhost:8000 (lần đầu khởi động mất ~1 phút nếu CPU yếu)
```
Dùng được trên máy chủ miễn phí 512 MB RAM, 0,1 CPU (khoảng 140 MB RAM khi chạy). Biến môi trường khác: `M28_DEMO_IDLE_S` (giây im lặng trước khi đặt lại, mặc định 300), `M28_DEMO_TASK_TTL_S` (tuổi tối đa của task demo trên CVAT, mặc định 1500).

## Ảnh mẫu và điều khoản dữ liệu
Ba đợt mẫu (`seed/NAP_001` 10 mặt, `NAP_002` 30 mặt, `NAP_003` 30 mặt) gồm 70 mặt, chỉ lấy ảnh cắt từ **video YawDD mà bảng của chủ bộ dữ liệu cho phép đăng ảnh** (cột "Allow Researchers to use picture in their paper" = Yes, đối chiếu qua bảng nội bộ của đội). Không có ảnh của video ghi "No", không có ảnh DrivFace (chỉ dùng học thuật). Trích dẫn: S. Abtahi, M. Omidyeganeh, S. Shirmohammadi, B. Hariri, "YawDD: A Yawning Detection Dataset", ACM Multimedia Systems, 2014. Chỉ dùng cho học tập và nghiên cứu, phi thương mại; không dùng lại ảnh ngoài mục đích đó.

Mỗi đợt đã qua pipeline thật (MediaPipe → 50 điểm DMS → cờ low_conf phiên bản 2 → gợi ý Ổn / Cần xem / nên Sửa nhãn).
