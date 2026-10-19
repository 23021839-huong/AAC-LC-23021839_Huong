"""One-command native FFT validation, AAC benchmarks, decode and plots on Windows."""
import argparse
from collections import Counter
import csv
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import uuid
from measure_distortion import inspect_adts,measure_files
ROOT=Path(__file__).resolve().parents[5]
sys.path.append(str(ROOT/'my_workspace/window_mdct/experiments/scripts'))
from run_window_experiments import validate_trace,write_csv,write_json

MODES=[("EXP01","ORIGINAL_FFT","original"),("EXP02","RADIX2_ONLY","radix2")]
FIELDS=["experiment_id","fft_mode","target_bitrate_kbps","actual_bitrate_kbps","encoding_time_mean_ms",
        "encoding_time_std_ms","fft_time_mean_ms","mse","snr_db","distortion_rate_percent","aac_size_bytes",
        "status","error","encoding_time_min_ms","encoding_time_max_ms","fft_time_std_ms","time_64_mean_ms","time_512_mean_ms",
        "payload_bitrate_kbps","header_bytes","aac_size_kib","source_duration_seconds","coded_duration_seconds","adts_frames",
        "sample_rate","channels","window_mode","source_samples_per_channel","compared_samples_per_channel","alignment_delay_samples",
        "alignment_correlation","trailing_padding_samples","fft_call_count","fft_calls_64","fft_calls_512","runs","profile_runs",
        "profile_encode_time_mean_ms","profile_encode_minus_main_mean_ms","clock_pair_mean_ns","estimated_clock_pair_cost_ms",
        "fft_fraction_of_profiled_encoder_percent","bitstream_shape_verified","window_sequences_equal","aac_sha256","run_id"]
RUN_FIELDS=["experiment_id","fft_mode","run_index","encoding_time_ms","aac_size_bytes","aac_sha256","status","run_id"]
PROFILE_FIELDS=["experiment_id","fft_mode","run_index","fft_length","fft_call_count","fft_time_ms","encoder_frames",
                "profile_encode_time_ms","exponent_increment","radix2_butterflies","radix4_butterflies","clock_pair_mean_ns","run_id"]


def publish_file(source,destination):
    # copy2 treats an existing directory as a container; published paths must be exact files.
    if destination.is_dir():
        raise IsADirectoryError(f"Expected output file, found directory: {destination}")
    shutil.copy2(source,destination)


def command(argv,log):
    log.parent.mkdir(parents=True,exist_ok=True)
    process=subprocess.run([str(a) for a in argv],capture_output=True,text=True)
    log.write_text("COMMAND: "+subprocess.list2cmdline([str(a) for a in argv])+"\n"+process.stdout+process.stderr,encoding="utf-8")
    if process.returncode:
        raise RuntimeError(f"Command exited {process.returncode}: {process.stderr.strip() or process.stdout[-1200:]}")


def build(build_dir,pre_capture,log_dir):
    if not shutil.which("cmake") or not shutil.which("ninja"):
        raise RuntimeError("CMake/Ninja must be on PATH")
    flags=["-G","Ninja","-DCMAKE_BUILD_TYPE=Release","-DBUILD_SHARED_LIBS=OFF","-DPSY_DEBUG=OFF","-DQUANT_DEBUG=OFF",
           "-DFDK_ENABLE_ENCODER_PROFILING=OFF","-DBUILD_PROGRAMS=OFF","-DBUILD_PSY_TRACE=OFF","-DBUILD_QUANT_TRACE=OFF"]
    flags += ["-DFFT_EXPERIMENT=OFF","-DWINDOW_EXPERIMENT=OFF","-DMDCT_DEBUG=ON","-DBUILD_MDCT_TRACE=ON"] if pre_capture else [
        "-DFFT_EXPERIMENT=ON","-DWINDOW_EXPERIMENT=ON","-DMDCT_DEBUG=OFF","-DBUILD_MDCT_TRACE=OFF"]
    command(["cmake","-S",ROOT,"-B",build_dir,*flags],log_dir/"configure.log")
    targets=["fdk_mdct_trace"] if pre_capture else ["fdk_fft_validate","fdk_fft_experiment","fdk_window_experiment"]
    command(["cmake","--build",build_dir,"--target",*targets,"--parallel","4"],log_dir/"build.log")


def collect_pre(args,native):
    if args.pre_long and args.pre_short:
        return args.pre_long.resolve(),args.pre_short.resolve()
    if args.pre_long or args.pre_short:
        raise ValueError("Supply both --pre-long and --pre-short, or neither")
    folder=ROOT/"build/fft_pre_capture"
    print("Collecting real PRE from unchanged ORIGINAL FFT encoder...",flush=True)
    build(folder,True,native/"pre_build_logs")
    exe=folder/("fdk_mdct_trace.exe" if sys.platform=="win32" else "fdk_mdct_trace")
    large=native/"pre_long_capture"
    command([exe,"--input",args.input,"--output-dir",large,"--frame","auto","--channel","0","--bitrate","64000"],large/"process.log")
    with (large/"frame_index.csv").open() as f:
        frames=list(csv.DictReader(f))
    short=next((r for r in frames if r["block_type"]=="SHORT" and r["channel"]=="0"),None)
    if short is None:
        raise ValueError("Input produced no native SHORT frame; supply a real --pre-short trace for FFT64 validation")
    small=native/"pre_short_capture"
    command([exe,"--input",args.input,"--output-dir",small,"--frame",short["frame"],"--channel","0","--bitrate","64000"],small/"process.log")
    return large/"02_preprocessing.txt",small/"02_preprocessing.txt"


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,default=ROOT/'my_workspace/INPUT/data/abc_votay.wav')
    parser.add_argument("--bitrate",type=int,default=64000)
    parser.add_argument("--runs",type=int,default=10)
    parser.add_argument("--output-dir",type=Path,default=ROOT/'my_workspace/window_mdct/experiments/fft')
    parser.add_argument("--build-dir",type=Path,default=ROOT/"build/fft_experiments")
    parser.add_argument("--binary",type=Path)
    parser.add_argument("--validator",type=Path)
    parser.add_argument("--pre-long",type=Path)
    parser.add_argument("--pre-short",type=Path)
    parser.add_argument("--skip-build",action="store_true")
    parser.add_argument("--no-plots",action="store_true")
    args=parser.parse_args(argv)
    if args.runs<10 or args.runs>1000:parser.error("Require 10..1000 measured runs per mode")
    if args.bitrate!=64000:parser.error("This controlled experiment requires 64000 bits/s")
    args.input=args.input.resolve();root=args.output_dir.resolve();build_dir=args.build_dir.resolve()
    suffix=".exe" if sys.platform=="win32" else ""
    binary=(args.binary or build_dir/("fdk_fft_experiment"+suffix)).resolve()
    validator=(args.validator or build_dir/("fdk_fft_validate"+suffix)).resolve()
    for name in ("encoded","decoded","results","plots","logs","runs"):(root/name).mkdir(parents=True,exist_ok=True)
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:6]
    native=root/"runs"/run_id;native.mkdir()
    status_path=root/"results/pipeline_status.json"
    status={"complete":False,"fft_validation_passed":False,"run_id":run_id,"input":str(args.input),"platform":platform.platform(),
            "decoder":"native FDK, ORIGINAL FFT","window_mode":"SINE_ONLY","runs_per_mode":args.runs,"profiling_separate":True,
            "tools":{name:shutil.which(name) for name in ("cmake","ninja","gcc","g++","python","ffmpeg")},"experiments":{}}
    rows=[];runs=[];profile_rows=[];sequence_reference=None
    write_json(status_path,status)
    try:
        if not args.skip_build:
            print("Building Release native Original/Radix2 FFT experiment...",flush=True)
            build(build_dir,False,native/"build_logs")
        long_pre,short_pre=collect_pre(args,native)
        numerical=native/"numerical"
        command([validator,"--output-dir",numerical,"--pre-long",long_pre,"--pre-short",short_pre],native/"validation.log")
        validation=json.loads((numerical/"fft_validation.json").read_text())
        if not validation.get("complete") or not validation.get("passed"):
            raise ValueError("FFT functional validation failed; AAC benchmarks prohibited")
        for name in ("fft_original.txt","fft_radix2.txt","fft_comparison.csv","fft_validation.json"):
            publish_file(numerical/name,root/"results"/name)
        status.update(fft_validation_passed=True,fft_bit_exact=validation["bit_exact"],numerical_cases=len(validation["cases"]),
                      pre_long=str(long_pre),pre_short=str(short_pre),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                      validator_sha256=hashlib.sha256(validator.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest())
        write_json(status_path,status)
        print(f"FFT gate PASS: {len(validation['cases'])} cases; bit exact={validation['bit_exact']}",flush=True)
        for eid,mode,name in MODES:
            folder=native/name;folder.mkdir()
            row={"experiment_id":eid,"fft_mode":mode,"target_bitrate_kbps":64,"status":"error","run_id":run_id}
            try:
                command([binary,"--input",args.input,"--output-dir",folder,"--mode",mode,"--runs",args.runs,
                         "--profile-runs",args.runs,"--bitrate",args.bitrate],folder/"process.log")
                meta=json.loads((folder/"run_metadata.json").read_text())
                if not meta.get("complete") or meta["fft_mode"]!=mode or meta["window_mode"]!="SINE_ONLY":
                    raise ValueError("Incomplete/wrong FFT or window configuration")
                times=meta["encoding_time_ms"];profiles=meta["profile_runs"]
                if len(times)!=args.runs or len(profiles)!=args.runs or meta["profiling_in_main_benchmark"]:
                    raise ValueError("Main timing/profile run separation or count invalid")
                with (folder/"frame_trace.csv").open() as f:trace=list(csv.DictReader(f))
                bitstream=inspect_adts((folder/"encoded.aac").read_bytes(),inspect_ics=True)
                sequence=validate_trace(trace,meta,[0,0,0,0],bitstream["frames"])
                if sequence_reference is None:sequence_reference=sequence
                elif sequence!=sequence_reference:raise ValueError("Window sequence changed with FFT mode")
                count512=sum(r["window_sequence_id"]!="2" for r in trace)
                count64=8*sum(r["window_sequence_id"]=="2" for r in trace)
                for p in profiles:
                    if (p["calls_64"],p["calls_512"])!=(count64,count512) or p["saturations"] or p["extra_prescale_calls"] or p["unexpected_lengths"]:
                        raise ValueError("FFT lengths/counts/scaling/saturation contract failed")
                    if (count64 and p["exponent_increment_64"]!=5) or (count512 and p["exponent_increment_512"]!=8):
                        raise ValueError("FFT exponent mismatch")
                    expected2=count64*192+count512*2304 if mode=="RADIX2_ONLY" else count64*128+count512*1792
                    expected4=0 if mode=="RADIX2_ONLY" else count64*16+count512*128
                    if (p["radix2_butterflies"],p["radix4_butterflies"])!=(expected2,expected4):
                        raise ValueError("Executed FFT backend/butterfly count mismatch")
                measured,_=measure_files(args.input,folder/"decoded.wav",meta["encoder_delay_samples"]+meta["decoder_additional_delay_samples"])
                if measured["metric_status"]!="ok":raise ValueError("Undefined distortion metrics")
                if measured["compared_samples_per_channel"]!=meta["source_samples_per_channel"]:raise ValueError("Incomplete source PCM coverage")
                row.update({k:v for k,v in bitstream.items() if k!="frames"})
                row.update({k:v for k,v in measured.items() if k in FIELDS})
                fft_times=[p["fft_time_ms"] for p in profiles];profile_times=[p["profile_encode_time_ms"] for p in profiles]
                row.update(error="",encoding_time_mean_ms=statistics.mean(times),encoding_time_std_ms=statistics.stdev(times),
                    encoding_time_min_ms=min(times),encoding_time_max_ms=max(times),fft_time_mean_ms=statistics.mean(fft_times),
                    fft_time_std_ms=statistics.stdev(fft_times),time_64_mean_ms=statistics.mean(p["time_64_ms"] for p in profiles),
                    time_512_mean_ms=statistics.mean(p["time_512_ms"] for p in profiles),distortion_rate_percent=measured["nrmse_percent"],
                    aac_size_kib=bitstream["aac_size_bytes"]/1024,window_mode="SINE_ONLY",source_samples_per_channel=meta["source_samples_per_channel"],
                    fft_call_count=count64+count512,fft_calls_64=count64,fft_calls_512=count512,runs=args.runs,profile_runs=args.runs,
                    profile_encode_time_mean_ms=statistics.mean(profile_times),profile_encode_minus_main_mean_ms=statistics.mean(profile_times)-statistics.mean(times),
                    clock_pair_mean_ns=meta["clock_pair_mean_ns"],estimated_clock_pair_cost_ms=(count64+count512)*meta["clock_pair_mean_ns"]/1e6,
                    fft_fraction_of_profiled_encoder_percent=100*statistics.mean(fft_times)/statistics.mean(profile_times),
                    bitstream_shape_verified=True,window_sequences_equal=True,aac_sha256=hashlib.sha256((folder/"encoded.aac").read_bytes()).hexdigest())
                write_json(folder/"distortion_alignment.json",measured)
                write_csv(folder/"bitstream_ics_trace.csv",bitstream["frames"],list(bitstream["frames"][0]))
                publish_file(folder/"encoded.aac",root/"encoded"/(name+".aac"))
                publish_file(folder/"decoded.wav",root/"decoded"/(name+"_decoded.wav"))
                for file in ("frame_trace.csv","bitstream_ics_trace.csv","run_metadata.json","distortion_alignment.json","process.log"):
                    publish_file(folder/file,root/"logs"/(name+"_"+file))
                row["status"]="ok" # Completion follows artifact publication.
                for i,t in enumerate(times,1):runs.append({"experiment_id":eid,"fft_mode":mode,"run_index":i,"encoding_time_ms":t,
                    "aac_size_bytes":row["aac_size_bytes"],"aac_sha256":row["aac_sha256"],"status":"ok","run_id":run_id})
                for p in profiles:
                    for length in (64,512):
                        calls=p[f"calls_{length}"]
                        profile_rows.append({"experiment_id":eid,"fft_mode":mode,"run_index":p["run_index"],"fft_length":length,
                            "fft_call_count":calls,"fft_time_ms":p[f"time_{length}_ms"],"encoder_frames":bitstream["adts_frames"],
                            "profile_encode_time_ms":p["profile_encode_time_ms"],"exponent_increment":p[f"exponent_increment_{length}"],
                            "radix2_butterflies":calls*(length//2)*((6 if length==64 else 9)-(0 if mode=="RADIX2_ONLY" else 2)),
                            "radix4_butterflies":0 if mode=="RADIX2_ONLY" else calls*(length//4),"clock_pair_mean_ns":meta["clock_pair_mean_ns"],"run_id":run_id})
                status["experiments"][eid]={"status":"ok","metrics":row,"native_directory":str(folder)}
                print(f"{eid} {mode}: encode {row['encoding_time_mean_ms']:.3f} +/- {row['encoding_time_std_ms']:.3f} ms; "
                      f"FFT {row['fft_time_mean_ms']:.3f} ms (separate profile); SNR {row['snr_db']:.3f} dB; {row['aac_size_bytes']} bytes",flush=True)
            except Exception as error:
                row.update(status="error",error=str(error));write_json(folder/"error.json",{"error":str(error)})
                status["experiments"][eid]={"status":"error","error":str(error)}
                print(f"{eid}: ERROR {error}",file=sys.stderr,flush=True)
            rows.append(row)
            write_csv(root/"results/fft_window_comparison.csv",rows,FIELDS)
            write_csv(root/"results/fft_runs.csv",runs,RUN_FIELDS)
            write_csv(root/"results/fft_profile.csv",profile_rows,PROFILE_FIELDS)
            write_json(status_path,status)
        if not all(r["status"]=="ok" for r in rows):return 1
        if validation["bit_exact"] and rows[0]["aac_sha256"]!=rows[1]["aac_sha256"]:
            raise ValueError("Bit-exact FFT validation but AAC streams differ; unresolved experimental variable")
        if not args.no_plots:
            from plot_fft_results import plot_results
            plot_results(root/"results/fft_window_comparison.csv",root/"plots")
        status.update(complete=True,window_sequences_equal=True,aac_outputs_bit_exact=rows[0]["aac_sha256"]==rows[1]["aac_sha256"])
        write_json(status_path,status)
        return 0
    except Exception as error:
        status.update(complete=False,error=str(error));write_json(status_path,status)
        if not rows:
            rows=[{"experiment_id":eid,"fft_mode":mode,"target_bitrate_kbps":64,"status":"error","error":str(error),"run_id":run_id} for eid,mode,_ in MODES]
        write_csv(root/"results/fft_window_comparison.csv",rows,FIELDS)
        write_csv(root/"results/fft_runs.csv",runs,RUN_FIELDS)
        write_csv(root/"results/fft_profile.csv",profile_rows,PROFILE_FIELDS)
        print("FFT experiment failed:",error,file=sys.stderr)
        return 1


if __name__=="__main__":raise SystemExit(main())
