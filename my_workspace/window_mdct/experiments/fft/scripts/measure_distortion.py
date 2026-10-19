"""Reuse the verified full-file alignment/MSE/SNR/NRMSE implementation."""
import importlib.util
from pathlib import Path
path=Path(__file__).resolve().parents[2]/"scripts/measure_distortion.py"
spec=importlib.util.spec_from_file_location("fdk_shared_distortion",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
inspect_adts=module.inspect_adts
measure_files=module.measure_files
align_pcm=module.align_pcm
distortion_metrics=module.distortion_metrics
read_pcm_wav=module.read_pcm_wav
