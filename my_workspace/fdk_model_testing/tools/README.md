# Tiện ích WAV dùng chung

- wav_pcm.h: khai báo TraceWav và read_trace_wav(path).
- wav_pcm.cpp: đọc RIFF/WAVE, kiểm tra header/chunk và chuyển dữ liệu mẫu về vector PCM16.
- Giữ sample rate và số kênh; không thực hiện resampling, MDCT hoặc mô hình tâm lý âm học.
- Hỗ trợ mono/stereo, PCM8/16/24/32 và IEEE float32/64 theo implementation hiện tại.
- Trường bits/format của TraceWav mô tả input; pcm chứa các mẫu int16_t sau chuyển đổi.
- Với bộ WAV PCM16 bàn giao, các mẫu đọc ra phải khớp nguyên giá trị với payload PCM gốc.
- Dùng C++17 do giao diện sử dụng std::filesystem.

CMakeLists.txt đã tham chiếu đúng đường dẫn này cho các runner nghiên cứu.
Hai file được sao chép nguyên byte từ workspace. wavreader.c ở gốc là reader riêng của CLI aac-enc; hai giao diện có các nơi sử dụng khác nhau.

Kiểm chứng phần 2 bao gồm sáu WAV PCM16 mono 48 kHz; chưa bao phủ toàn bộ định dạng hỗ trợ.
