// Verification only: native fixed-point FFT vs pure radix2 vs direct double DFT.
#include "fft_experiment.h"
#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs=std::filesystem;
namespace {
constexpr double pi=3.1415926535897932384626433832795;
struct Case {std::string name;int length,exponent;std::vector<FIXP_DBL> data;};
struct Result {
  std::string name;int length,eo,er,extra,stages,bits;
  double maximum=0,mae=0,rmse=0,dft_error=0,bound=0;
  INT64 butterflies=0,saturations=0;bool passed=false;
};
std::vector<FIXP_DBL> read_pre(const fs::path &path) {
  std::ifstream f(path);if(!f)throw std::runtime_error("Cannot read PRE: "+path.string());
  std::vector<FIXP_DBL> data;long long index,re,im;
  while(f>>index>>re>>im) {
    if(index!=static_cast<long long>(data.size()/2) || re<(-2147483647LL-1) || re>2147483647LL || im<(-2147483647LL-1) || im>2147483647LL)
      throw std::runtime_error("Invalid PRE index/value");
    data.push_back(FIXP_DBL(re));data.push_back(FIXP_DBL(im));
  }
  if(!f.eof() || data.size()!=1024)throw std::runtime_error("Incomplete PRE input");
  return data;
}
std::vector<Case> cases(const fs::path &long_pre,const fs::path &short_pre) {
  std::vector<Case> out;
  for(int n:{64,512}) {
    Case c={"zero",n,0,std::vector<FIXP_DBL>(2*n,0)};out.push_back(c);
    c.name="impulse";c.data[0]=1<<27;out.push_back(c);
    c.name="complex_impulse";std::fill(c.data.begin(),c.data.end(),0);c.data[34]=-(1<<27);c.data[35]=1<<26;out.push_back(c);
    for(bool complex:{false,true}) {
      c.name=complex?"complex_tone":"real_sine";
      for(int i=0;i<n;++i) {double a=2*pi*7*i/n;
        c.data[2*i]=FIXP_DBL(std::llround((1<<27)*(complex?std::cos(a):std::sin(a))));
        c.data[2*i+1]=complex?FIXP_DBL(std::llround((1<<27)*std::sin(a))):0;}
      out.push_back(c);
    }
    for(unsigned seed=0;seed<4;++seed) {
      std::uint32_t state=1234567+seed;c.name="random_"+std::to_string(seed);
      for(auto &v:c.data) {state=1664525u*state+1013904223u;v=FIXP_DBL(INT64(state&0x1fffffff)-0x10000000);}
      out.push_back(c);
    }
    c.name="full_scale";std::fill(c.data.begin(),c.data.end(),FIXP_DBL(2147483647));out.push_back(c);
    c.name="int_min";for(int i=0;i<n;++i){c.data[2*i]=FIXP_DBL(-2147483647-1);c.data[2*i+1]=0;}out.push_back(c);
    c.name="boundary_alternating";for(int i=0;i<2*n;++i)c.data[i]=(i%3)?FIXP_DBL(2147483647):FIXP_DBL(-2147483647-1);out.push_back(c);
  }
  out.push_back(Case{"pre_long",512,2,read_pre(long_pre)});
  auto small=read_pre(short_pre);
  for(int sub=0;sub<8;++sub)out.push_back(Case{"pre_short_"+std::to_string(sub),64,2,
    std::vector<FIXP_DBL>(small.begin()+128*sub,small.begin()+128*(sub+1))});
  return out;
}
Result check(const Case &c,std::ostream &csv,std::ostream &original_dump,std::ostream &radix2_dump) {
  alignas(32) FIXP_DBL original[1028]={},radix2[1028]={};
  std::copy(c.data.begin(),c.data.end(),original);std::copy(c.data.begin(),c.data.end(),radix2);
  for(int i=2*c.length;i<1028;++i)original[i]=radix2[i]=0x12345678;
  int eo=c.exponent,er=c.exponent;FDK_FFT_DIAGNOSTICS a{},b{};
  if(FDKfftExperimentTransform(FFT_ORIGINAL,c.length,original,&eo,&a) || FDKfftExperimentTransform(FFT_RADIX2_ONLY,c.length,radix2,&er,&b))
    throw std::runtime_error("FFT rejected validation input");
  for(int i=2*c.length;i<1028;++i)if(original[i]!=0x12345678 || radix2[i]!=0x12345678)throw std::runtime_error("FFT buffer overwrite");
  Result r;r.name=c.name;r.length=c.length;r.eo=eo;r.er=er;r.extra=b.extra_prescale;
  r.stages=b.stages;r.bits=b.coefficient_fraction_bits;r.butterflies=b.radix2_butterflies;r.saturations=b.saturations;
  std::vector<std::complex<double>> roots(c.length),input(c.length);double peak=0;
  for(int i=0;i<c.length;++i) {
    roots[i]=std::polar(1.0,-2*pi*i/c.length);
    double re=std::floor(std::ldexp(double(c.data[2*i]),-r.extra)),im=std::floor(std::ldexp(double(c.data[2*i+1]),-r.extra));
    input[i]={re,im};peak=std::max({peak,std::abs(re),std::abs(im)});
  }
  for(int k=0;k<c.length;++k) {
    std::complex<double> dft={0,0};for(int i=0;i<c.length;++i)dft+=input[i]*roots[(i*k)%c.length];
    dft/=double(1<<(r.stages-1));
    r.dft_error=std::max({r.dft_error,std::abs(double(radix2[2*k])-dft.real()),std::abs(double(radix2[2*k+1])-dft.imag())});
    INT64 re=INT64(radix2[2*k])-original[2*k],im=INT64(radix2[2*k+1])-original[2*k+1];
    r.maximum=std::max({r.maximum,std::abs(double(re)),std::abs(double(im))});
    r.mae+=std::abs(double(re))+std::abs(double(im));r.rmse+=double(re)*re+double(im)*im;
    csv<<k<<','<<original[2*k]<<','<<original[2*k+1]<<','<<radix2[2*k]<<','<<radix2[2*k+1]<<','<<re<<','<<im<<','<<c.name<<','<<c.length<<','<<eo<<','<<er<<'\n';
    original_dump<<c.name<<' '<<c.length<<' '<<k<<' '<<original[2*k]<<' '<<original[2*k+1]<<' '<<eo<<'\n';
    radix2_dump<<c.name<<' '<<c.length<<' '<<k<<' '<<radix2[2*k]<<' '<<radix2[2*k+1]<<' '<<er<<'\n';
  }
  r.mae/=2*c.length;r.rmse=std::sqrt(r.rmse/(2*c.length));
  r.bound=4*peak*r.stages/std::ldexp(1.0,r.bits)+8*r.stages;
  r.passed=r.maximum<=64 && eo==er && !r.saturations && !b.radix4_butterflies &&
    r.butterflies==INT64(c.length/2)*r.stages && r.dft_error<=r.bound;
  return r;
}
}
int main(int argc,char **argv) {
  fs::path folder="my_workspace/window_mdct/experiments/fft/results",large="my_workspace/window_mdct/output/02_preprocessing.txt",small="my_workspace/window_mdct/output/mdct_short_example/02_preprocessing.txt";
  try {
    for(int i=1;i<argc;++i){std::string a=argv[i];if(++i>=argc)throw std::runtime_error("Missing value");
      if(a=="--output-dir")folder=argv[i];else if(a=="--pre-long")large=argv[i];else if(a=="--pre-short")small=argv[i];else throw std::runtime_error("Unknown option: "+a);}
    fs::create_directories(folder);
    {std::ofstream f(folder/"fft_validation.json");f<<"{\"complete\":false,\"passed\":false}\n";if(!f)throw std::runtime_error("Cannot create validation status");}
    auto inputs=cases(large,small);
    std::ofstream csv(folder/"fft_comparison.csv"),original(folder/"fft_original.txt"),radix2(folder/"fft_radix2.txt");
    if(!csv || !original || !radix2)throw std::runtime_error("Cannot write FFT dumps");
    csv<<"index,original_real,original_imag,radix2_real,radix2_imag,error_real,error_imag,case,length,original_exponent,radix2_exponent\n";
    original<<"# case length index real imag exponent\n";radix2<<"# case length index real imag exponent\n";
    std::vector<Result> results;bool passed=true,exact=true;double maximum=0;
    for(const auto &input:inputs){auto r=check(input,csv,original,radix2);passed&=r.passed;exact&=r.maximum==0;maximum=std::max(maximum,r.maximum);results.push_back(r);}
    csv.close();original.close();radix2.close();if(!csv || !original || !radix2)throw std::runtime_error("Cannot finish FFT dumps");
    std::ofstream f(folder/"fft_validation.json");f<<std::setprecision(17)
      <<"{\"complete\":true,\"passed\":"<<(passed?"true":"false")<<",\"bit_exact\":"<<(exact?"true":"false")
      <<",\"supported_lengths\":[64,512],\"allowed_original_max_abs_error\":64,\"maximum_absolute_error\":"<<maximum
      <<",\"reference\":\"independent direct double DFT, used only for validation\",\"cases\":[";
    for(std::size_t i=0;i<results.size();++i){if(i)f<<',';const auto &r=results[i];f<<"{\"case\":\""<<r.name<<"\",\"length\":"<<r.length
      <<",\"max_abs_error\":"<<r.maximum<<",\"mean_abs_error\":"<<r.mae<<",\"rmse\":"<<r.rmse
      <<",\"original_exponent\":"<<r.eo<<",\"radix2_exponent\":"<<r.er<<",\"exponent_difference\":"<<r.er-r.eo
      <<",\"extra_prescale\":"<<r.extra<<",\"stages\":"<<r.stages<<",\"coefficient_fraction_bits\":"<<r.bits
      <<",\"radix2_butterflies\":"<<r.butterflies<<",\"radix4_butterflies\":0,\"saturation_count\":"<<r.saturations
      <<",\"direct_dft_max_error\":"<<r.dft_error<<",\"direct_dft_error_bound\":"<<r.bound<<",\"passed\":"<<(r.passed?"true":"false")<<'}';}
    f<<"]}\n";f.close();if(!f)throw std::runtime_error("Cannot finish validation status");
    std::cout<<"FFT validation: "<<results.size()<<" cases, max error="<<maximum<<", bit exact="<<exact<<", passed="<<passed<<'\n';return passed?0:1;
  }catch(const std::exception &e){std::cerr<<"Validation error: "<<e.what()<<'\n';return 1;}
}
