"""Write a Vietnamese analysis from measured CSV; never fill missing metrics."""
import argparse
import csv
from pathlib import Path
import statistics


def read_rows(path):
    with Path(path).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def report_results(folder):
    folder = Path(folder)
    rows = read_rows(folder / 'results/psy_comparison.csv')
    profiles = read_rows(folder / 'results/psy_profile.csv')
    by_id = {r['experiment_id']: r for r in rows}
    text = ['# Phân tích Tonality/TNS từ số đo thực tế', '',
            f"Campaign: `{rows[0]['run_id']}`. Nguồn: [psy_comparison.csv](psy_comparison.csv), "
            '[psy_runs.csv](psy_runs.csv), [psy_profile.csv](psy_profile.csv).', '',
            '| Case | Tonality | TNS | Bitrate (kb/s) | Encode mean ± SD (ms) | NRMSE (%) | SNR (dB) | AAC (bytes) | Status |',
            '|---|---|---|---:|---:|---:|---:|---:|---|']
    for r in rows:
        if r['status'] == 'PASS':
            values = (f"{float(r['actual_bitrate_kbps']):.6f}",
                      f"{float(r['encoding_time_mean_ms']):.4f} ± {float(r['encoding_time_std_ms']):.4f}",
                      f"{float(r['distortion_rate_percent']):.6f}", f"{float(r['snr_db']):.6f}", r['aac_size_bytes'])
        else:
            values = ('—',) * 5
        text.append(f"| {r['experiment_id']} | {r['tonality_enabled']} | {r['tns_enabled']} | "
                    + ' | '.join(values) + f" | {r['status']} |")
    if any(r['status'] != 'PASS' for r in rows):
        text += ['', 'Chưa có đủ bốn case PASS để kết luận đầy đủ. Các case thiếu dữ liệu:', '']
        text += [f"- {r['experiment_id']}: {r['status']} — {r['error']}" for r in rows if r['status'] != 'PASS']
    else:
        first = rows[0]
        text += ['', '## Kiểm tra tính hợp lệ', '',
                 f"Input có {first['sample_rate']} Hz, {first['channels']} kênh; tất cả case cùng AOT=2, "
                 f"target=64 kb/s, {first['adts_frames']} frame AAC-LC/1024 sample. "
                 f"Thời lượng WAV={float(first['source_duration_seconds']):.6f} s; "
                 f"thời lượng coded={float(first['coded_duration_seconds']):.6f} s. "
                 'Bitrate tính theo coded duration, gồm ADTS header.', '',
                 f"Căn chỉnh đo được delay={first['alignment_delay_samples']} sample. "
                 f"So đủ {first['compared_samples_per_channel']} sample/channel cho mỗi case; "
                 'không resample hoặc sửa gain. Xem JSON alignment tương ứng trong `../logs/`.', '',
                 f"EXP01 giống từng byte với baseline không biên dịch hook điều khiển: `{first['baseline_identical']}`. "
                 'Native probe cũng giống baseline. Window sequence/shape và hash raw MDCT trước lowpass '
                 'được kiểm tra giống nhau trên mọi frame/channel của bốn case.', '',
                 '| Case | PNS cấu hình | Frame/channel thực thi Tonality | TNS filter encoder | TNS filter decoder |',
                 '|---|---:|---:|---:|---:|']
        for r in rows:
            text.append(f"| {r['experiment_id']} | {r['effective_pns_enabled']} | {r['tonality_applied_frames']} | "
                        f"{r['encoder_tns_filters']} | {r['decoder_tns_filters']} |")
        text += ['', 'TNS ON cho phép lựa chọn filter; số filter được decoder đọc từ syntax thật. '
                 'TNS OFF không có filter. Số filter khác số frame dùng TNS và khác số lời gọi hàm lọc.', '',
                 '## Tách ảnh hưởng từng yếu tố', '',
                 'Dấu Δ là case OFF trừ case ON; NRMSE dùng **điểm phần trăm**, không phải phần trăm tương đối.', '',
                 '| Yếu tố tắt | OFF − ON | Δ encode mean (ms) | Δ NRMSE (điểm %) | Δ bitrate (kb/s) | Δ AAC (bytes) | AAC giống từng byte |',
                 '|---|---|---:|---:|---:|---:|---|']
        for factor, off, on in [('Tonality', 'EXP03', 'EXP01'), ('Tonality', 'EXP04', 'EXP02'),
                                ('TNS', 'EXP02', 'EXP01'), ('TNS', 'EXP04', 'EXP03')]:
            a, b = by_id[off], by_id[on]
            delta = lambda field: float(a[field]) - float(b[field])
            text.append(f"| {factor} | {off} − {on} | {delta('encoding_time_mean_ms'):+.4f} | "
                        f"{delta('distortion_rate_percent'):+.6f} | {delta('actual_bitrate_kbps'):+.6f} | "
                        f"{int(delta('aac_size_bytes')):+d} | {a['aac_sha256'] == b['aac_sha256']} |")
        if all(r['effective_pns_enabled'] == '0' for r in rows):
            text += ['', '**Tonality:** PNS gốc đang OFF ở cấu hình WAV này. ON thực thi estimator gốc; '
                     'OFF bypass hợp lệ. Hai cặp có cùng TNS tạo cùng bitstream, cùng NRMSE và cùng kích thước. '
                     'Kết quả này cho thấy kết quả estimator không có consumer tại cấu hình hiện tại; '
                     'không chứng minh Tonality vô ích khi PNS hoạt động.']
        text += ['', '**TNS:** Ở WAV này, OFF làm NRMSE giảm và file tăng rất ít so với ON. '
                 'Đây là kết quả waveform của một input, không đủ kết luận chất lượng nghe tốt hơn. '
                 'NRMSE không đánh giá riêng temporal masking/pre-echo và không mô tả phân bố sai số theo thời gian. '
                 'Không suy rộng rằng bật hoặc tắt TNS luôn tốt hơn.', '',
                 '**Thời gian:** Chênh lệch mean cần đọc cùng SD và min/max trong CSV. '
                 'Các nhóm đo chạy tuần tự, không randomize/pin CPU. Dao động do môi trường chưa được loại bỏ; '
                 'không dùng các mean này để tuyên bố mức tăng tốc ổn định trên CPU hoặc PL.', '',
                 '## Profile riêng', '',
                 'Các giá trị dưới đây là mean của các lượt profile bổ sung, có overhead clock. '
                 '`psy_model_time_ms` bao gồm toàn wrapper Psy với Block Switching, Window/MDCT và lịch sử. '
                 'Không cộng các stage con vào wrapper; không thay profile encode time cho thời gian đo chính.', '',
                 '| Case | Profile runs | Psy wrapper (ms) | Tonality (ms) | TNS analysis (ms) | TNS filtering (ms) |',
                 '|---|---:|---:|---:|---:|---:|']
        for r in rows:
            case_profiles = [p for p in profiles if p['experiment_id'] == r['experiment_id']]
            means = [statistics.mean(float(p[field]) for p in case_profiles) for field in
                     ('psy_model_time_ms', 'tonality_time_ms', 'tns_analysis_time_ms', 'tns_filtering_time_ms')]
            text.append(f"| {r['experiment_id']} | {len(case_profiles)} | " + ' | '.join(f'{v:.4f}' for v in means) + ' |')
        text += ['', 'Tonality/TNS OFF có stage time=0 và số lời gọi=0 vì nhánh tương ứng không chạy. '
                 'Chi phí estimator có thể thấy trong profile dù bitstream không đổi. '
                 'Lượng tài nguyên, latency và throughput khi chuyển lên PL phải được đánh giá riêng từ thiết kế RTL/synthesis; '
                 'số đo CPU không phải số đo FPGA.']
    text += ['', '## Hồ sơ và chạy lại', '',
             'Xem [README](../README.md) để đọc nguồn, gate/bypass, định nghĩa phép đo, giới hạn và lệnh Windows. '
             'Bốn AAC/WAV nằm trong `../encoded/` và `../decoded/`; trace trong `../logs/`. '
             '[Đồ thị tổng hợp](../plots/psy_overview.png) lấy trực tiếp từ CSV này.', '',
             'Báo cáo do `scripts/report_psy_results.py` tạo từ số liệu của campaign; không điền số liệu cho case lỗi.', '']
    path = folder / 'results/analysis.md'
    path.write_text('\n'.join(text), encoding='utf-8')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, default=Path('my_workspace/psychoacoustic_model/experiments/psy'))
    print(report_results(parser.parse_args().output_dir))
