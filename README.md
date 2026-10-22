# noise-cut

Ứng dụng lọc giọng nói realtime cho Windows — loại bỏ tạp âm (gõ phím, quạt, điều hòa, ù nền), nhẹ và đơn giản. Dùng cho **Google Meet / Zoom / Teams / Discord / OBS** thông qua mic ảo.

## Tính năng

- Lọc ồn realtime bằng **RNNoise** (mặc định, nhẹ, có high-pass 80 Hz) hoặc **DeepFilterNet3** (tùy chọn, lọc mạnh hơn) + slider mức khử có nhãn **Nhẹ ↔ Mạnh**
- Giao diện ưu tiên trạng thái: card **ĐANG KHỬ ỒN / KHỬ ỒN ĐANG TẮT**, nút bật/tắt lớn, đồng hồ tín hiệu **Vào/Ra** realtime; các thiết lập phụ nằm trong **Cài đặt nâng cao**
- Mic ảo **VB-CABLE** tích hợp: bấm **"Cài mic ảo"** trong app là xong (tự tải kèm sẵn, mở UAC, không cần lên web)
- **Thanh nhỏ luôn nổi** (always-on-top): kéo được, luôn hiển thị kể cả khi cửa sổ chính ẩn xuống tray; có nút giữ để tắt tiếng và nút hướng dẫn
- **Tắt tiếng tức thì** (khi ho/hắt xì): giữ **Ctrl+Shift+?** (phím `/`) — thả ra để nói tiếp; hoặc giữ nút **GIỮ ĐỂ TẮT TIẾNG** trong **Cài đặt nâng cao**/thanh nhỏ; có chế độ bấm 1 lần để bật/tắt
- Tự bật lọc khi mở app, thu nhỏ xuống **khay hệ thống**, bật/tắt nhanh từ menu tray
- Tùy chọn **tự chạy cùng Windows**, nhớ thiết bị + độ lọc + bộ lọc
- Nhẹ: RAM ~55 MB (RNNoise) / ~80 MB (DFN3); CPU RNNoise ~1% tổng; DFN3 ~0.18 RTF; trễ xử lý nội bộ ~60 ms (RNNoise) / ~70 ms (DFN3)

## Dùng nhanh (bản exe)

1. Chạy `dist-folder\noise-cut\noise-cut.exe` (khởi động ~1s, khuyên dùng hằng ngày; DFN3 load model thêm ~0.2s)
   hoặc `dist\noise-cut.exe` (1 file duy nhất ~59 MB, khởi động ~3–4s).
2. Bấm **Cài mic ảo (VB-Cable)** → bấm **Yes** ở hộp thoại UAC → **khởi động lại Windows**.
3. Mở app: tự chọn `CABLE Input` và tự bật lọc. Mở **Cài đặt nâng cao** để chọn bộ lọc nếu muốn dùng DFN3.
4. Trong Meet/Zoom/Teams chọn micro là **CABLE Output (VB-Audio Virtual Cable)** và **tắt khử ồn có sẵn** của chúng (tránh lọc 2 lần méo tiếng).
5. Bấm **X** để thu nhỏ xuống khay (bộ lọc vẫn chạy); thoát hẳn bằng menu chuột phải ở khay.

> Lần đầu chạy Windows có thể hiện cảnh báo SmartScreen (exe chưa ký chứng chỉ) → chọn *More info → Run anyway*.

## Chọn RNNoise hay DFN3?

- **RNNoise** (mặc định): nhẹ, ổn định, phù hợp hầu hết mic; xử lý tốt quạt/điều hòa/ù nền nhẹ.
- **DFN3**: lọc mạnh hơn với ồn nền khó (quạt, gió, công trường, nhiều người nói), nhưng **không phải BVC/AEC như Krisp**: tiếng người xung quanh và echo vẫn có thể lọt; ho/hắt xì vẫn nên dùng nút tắt tiếng.
- Benchmark synthetic en-US: tại SNR +5 dB, DFN3 giảm noise trung bình **7.4 dB** so với **0.6 dB** của RNNoise; SI-SDR/STOI cao hơn. Chi tiết và hạn chế tại `bench/report.md`.
- DFN3 dùng package alpha `deepfilternet-rs==0.1.1` (MIT), model 8 MB đóng gói sẵn; chưa có benchmark tiếng Việt.

## Chạy từ source (dev)

```bat
setup.bat   :: tạo venv + cài thư viện (cần Python 3.12)
run.bat     :: mở app
build.bat   :: đóng gói lại 2 bản .exe (cần PyInstaller, tự cài)
```

Thư viện runtime: `numpy`, `sounddevice`, `soxr`, `pystray`, `pillow`, `pynput`; DFN3 dùng thêm `deepfilternet-rs==0.1.1` (MIT, đã pin để tránh package alpha thay đổi).

## Tắt tiếng nhanh (ho / hắt xì / hét)

Cả RNNoise và DFN3 đều không đảm bảo chặn ho/hét (DFN3 có thể giảm mạnh ho nhưng vẫn lọt hắt xì/tiếng người). Cách chuẩn là tắt tiếng tức thì:

- Phím tắt toàn cục duy nhất: **Ctrl+Shift+?** (giữ `Ctrl` + `Shift` + phím `/`, tức phím `?`; bấm được cả khi app ẩn dưới tray). Không chặn phím, nên tổ hợp vẫn được gửi tới app đang focus.
  - Mặc định: **giữ** để tắt tiếng, thả ra để mở lại.
  - Tick **"Bấm 1 lần để bật/tắt"** để chuyển sang chế độ toggle.
- Nút **GIỮ ĐỂ TẮT TIẾNG** trong **Cài đặt nâng cao** và trên **thanh nhỏ luôn nổi**: cùng cơ chế giữ-thả.
- Trạng thái đỏ **ĐANG TẮT TIẾNG** trên cửa sổ chính + menu tray "Tắt tiếng" hiển thị trạng thái.
- Thanh nhỏ luôn nổi có thể kéo bằng chuột; vị trí được nhớ. Ẩn/hiện bằng menu tray **"Hiện/Ẩn thanh nhỏ"** (nên ẩn khi chia sẻ toàn màn hình, vì cửa sổ nổi sẽ bị lộ).

## Cấu trúc

```
app.py                 :: điểm vào
noisecut/
  gui.py               :: giao diện tkinter + tray
  mini.py              :: thanh nhỏ luôn nổi, kéo được, nút tắt tiếng
  toast.py             :: thông báo nhỏ khi thu nhỏ xuống tray
  hotkey.py            :: phím tắt toàn cục Ctrl+Shift+/? (pynput)
  engine.py            :: thu mic → xử lý → ghi ra mic ảo (ring buffer, resample, DFN3 worker)
  denoiser.py          :: high-pass NumPy + RNNoise + dry/wet mix
  dfn3.py              :: DeepFilterNet3 streaming + delay-align cho dry/wet mix
  rnnoise.py           :: nạp rnnoise.dll bằng ctypes (không kéo audiolab/matplotlib)
  rnnoise.dll          :: thư viện RNNoise (BSD-3, xem RNNOISE_LICENSE.txt)
  vbcable.py           :: giải nén + chạy installer VB-CABLE qua UAC (runas, -i -h)
  config.py            :: config %APPDATA%\noise-cut + tự chạy cùng Windows (registry)
  vendor/              :: gói VB-CABLE nguyên bản + VBCABLE_NOTICE.txt
assets/icon.ico        :: icon app + tray
```

## Kiểm tra nhanh

```bat
venv\Scripts\python.exe -m py_compile app.py noisecut\*.py
```

- Denoiser: ồn trắng −58 dB sau lọc, giọng giữ −9 dB.
- Engine: mic → CABLE Input chạy ổn định, không lỗi callback; DFN3 worker nhận frame 480 và trả output đúng độ dài.
- GUI: auto-start khi có cable, tray ẩn/hiện, toggle, autorun registry, cài 1-click chống bấm kép; đổi bộ lọc khi đang chạy.
- Mute: giữ `Ctrl+Shift+?` → thanh nhỏ chuyển đỏ; thả → trở lại; vị trí thanh nhỏ được nhớ sau khi khởi động lại.
- DFN3: model load trong worker thread, không chặn audio callback; `dist-folder` đã chạy DFN3 với CABLE Input.

## Ghi chú kỹ thuật

- Endpoint "CABLE Input" là **playback** (app ghi âm đã lọc vào đây), "CABLE Output" là **capture** (Meet/Zoom/Teams chọn làm micro).
- PortAudio cache danh sách thiết bị theo tiến trình: sau khi cài driver nên **restart app** (khuyên reboot theo tài liệu VB-Cable).
- Nếu mic/loa không phải 48 kHz, app tự resample bằng soxr.

## Bản quyền / attribution

- **VB-CABLE** là donationware của VB-Audio — nguồn: www.vb-cable.com. Gói trong `noisecut/vendor/` là bản gốc không sửa đổi, nhúng kèm theo điều khoản tại https://vb-audio.com/Services/licensing.htm (chỉ gói CABLE gốc, không kèm A+B/C+D).
- **RNNoise** © Xiph.Org Foundation và cộng tác viên, giấy phép BSD-3-Clause (`noisecut/RNNOISE_LICENSE.txt`).
- **DeepFilterNet3** © DeepFilterNet contributors; **deepfilternet-rs** bindings, giấy phép MIT; model DeepFilterNet3 đóng gói trong package.
- **pynput** © Moses Palmér, giấy phép LGPL-3.0 (dùng cho phím tắt toàn cục).
- Code noise-cut: dùng cá nhân tự do; khi phân phối kèm VB-CABLE cho tổ chức/doanh nghiệp cần mua license theo chính sách của VB-Audio.
