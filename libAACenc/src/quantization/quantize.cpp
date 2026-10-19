/* -----------------------------------------------------------------------------
Software License for The Fraunhofer FDK AAC Codec Library for Android

© Copyright  1995 - 2018 Fraunhofer-Gesellschaft zur Förderung der angewandten
Forschung e.V. All rights reserved.

 1.    INTRODUCTION
The Fraunhofer FDK AAC Codec Library for Android ("FDK AAC Codec") is software
that implements the MPEG Advanced Audio Coding ("AAC") encoding and decoding
scheme for digital audio. This FDK AAC Codec software is intended to be used on
a wide variety of Android devices.

AAC's HE-AAC and HE-AAC v2 versions are regarded as today's most efficient
general perceptual audio codecs. AAC-ELD is considered the best-performing
full-bandwidth communications codec by independent studies and is widely
deployed. AAC has been standardized by ISO and IEC as part of the MPEG
specifications.

Patent licenses for necessary patent claims for the FDK AAC Codec (including
those of Fraunhofer) may be obtained through Via Licensing
(www.vialicensing.com) or through the respective patent owners individually for
the purpose of encoding or decoding bit streams in products that are compliant
with the ISO/IEC MPEG audio standards. Please note that most manufacturers of
Android devices already license these patent claims through Via Licensing or
directly from the patent owners, and therefore FDK AAC Codec software may
already be covered under those patent licenses when it is used for those
licensed purposes only.

Commercially-licensed AAC software libraries, including floating-point versions
with enhanced sound quality, are also available from Fraunhofer. Users are
encouraged to check the Fraunhofer website for additional applications
information and documentation.

2.    COPYRIGHT LICENSE

Redistribution and use in source and binary forms, with or without modification,
are permitted without payment of copyright license fees provided that you
satisfy the following conditions:

You must retain the complete text of this software license in redistributions of
the FDK AAC Codec or your modifications thereto in source code form.

You must retain the complete text of this software license in the documentation
and/or other materials provided with redistributions of the FDK AAC Codec or
your modifications thereto in binary form. You must make available free of
charge copies of the complete source code of the FDK AAC Codec and your
modifications thereto to recipients of copies in binary form.

The name of Fraunhofer may not be used to endorse or promote products derived
from this library without prior written permission.

You may not charge copyright license fees for anyone to use, copy or distribute
the FDK AAC Codec software or your modifications thereto.

Your modified versions of the FDK AAC Codec must carry prominent notices stating
that you changed the software and the date of any change. For modified versions
of the FDK AAC Codec, the term "Fraunhofer FDK AAC Codec Library for Android"
must be replaced by the term "Third-Party Modified Version of the Fraunhofer FDK
AAC Codec Library for Android."

3.    NO PATENT LICENSE

NO EXPRESS OR IMPLIED LICENSES TO ANY PATENT CLAIMS, including without
limitation the patents of Fraunhofer, ARE GRANTED BY THIS SOFTWARE LICENSE.
Fraunhofer provides no warranty of patent non-infringement with respect to this
software.

You may use this FDK AAC Codec software or modifications thereto only for
purposes that are authorized by appropriate patent licenses.

4.    DISCLAIMER

This FDK AAC Codec software is provided by Fraunhofer on behalf of the copyright
holders and contributors "AS IS" and WITHOUT ANY EXPRESS OR IMPLIED WARRANTIES,
including but not limited to the implied warranties of merchantability and
fitness for a particular purpose. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
CONTRIBUTORS BE LIABLE for any direct, indirect, incidental, special, exemplary,
or consequential damages, including but not limited to procurement of substitute
goods or services; loss of use, data, or profits, or business interruption,
however caused and on any theory of liability, whether in contract, strict
liability, or tort (including negligence), arising in any way out of the use of
this software, even if advised of the possibility of such damage.

5.    CONTACT INFORMATION

Fraunhofer Institute for Integrated Circuits IIS
Attention: Audio and Multimedia Departments - FDK AAC LL
Am Wolfsmantel 33
91058 Erlangen, Germany

www.iis.fraunhofer.de/amm
amm-info@iis.fraunhofer.de
----------------------------------------------------------------------------- */

/**************************** AAC encoder library ******************************

   Author(s):   M.Werner

   Description: Quantization

*******************************************************************************/

#include "quantize.h"
#include "quant_debug.h"

#define Q_LINE(name,value,fraction,exp,unit) QUANT_OBSERVE(if(FDKquantDebugWantLines())FDKquantDebugScalar("quantization","line." name,(long long)(value),32,fraction,exp,unit,FDKquantDebugLine()))

#include "aacEnc_rom.h"
#include "aacenc_profile.h"

/*****************************************************************************

    functionname: FDKaacEnc_quantizeLines
    description: quantizes spectrum lines
    returns:
    input: global gain, number of lines to process, spectral data
    output: quantized spectrum

*****************************************************************************/
static void FDKaacEnc_quantizeLines(INT gain, INT noOfLines,
                                    const FIXP_DBL *mdctSpectrum,
                                    SHORT *quaSpectrum, INT dZoneQuantEnable) {
  QUANT_OBSERVE(FDKquantDebugRange(mdctSpectrum,noOfLines,gain));
  int line;
  FIXP_DBL k = FL2FXCONST_DBL(0.0f);
  FIXP_QTD quantizer = FDKaacEnc_quantTableQ[(-gain) & 3];
  INT quantizershift = ((-gain) >> 2) + 1;
  const INT kShift = 16;

  if (dZoneQuantEnable)
    k = FL2FXCONST_DBL(0.23f) >> kShift;
  else
    k = FL2FXCONST_DBL(-0.0946f + 0.5f) >> kShift;

  for (line = 0; line < noOfLines; line++) {
    QUANT_OBSERVE(FDKquantDebugLineOffset(line));
    FIXP_DBL accu = fMultDiv2(mdctSpectrum[line], quantizer);
    Q_LINE("input",mdctSpectrum[line],31,FDKquantDebugScale(),"pcm");
    Q_LINE("gain",gain,0,0,"integer");
    Q_LINE("mul_q",accu,31,0,"internal");
    Q_LINE("round_offset",k,31,0,"internal");

    if (accu < FL2FXCONST_DBL(0.0f)) {
      accu = -accu;
      /* normalize */
      INT accuShift = CntLeadingZeros(accu) - 1; /* CountLeadingBits() is not
                                                    necessary here since test
                                                    value is always > 0 */
      accu <<= accuShift;
      Q_LINE("clz",accuShift,0,0,"integer");
      Q_LINE("normalized",accu,31,0,"internal");
      INT tabIndex =
          (INT)(accu >> (DFRACT_BITS - 2 - MANT_DIGITS)) & (~MANT_SIZE);
      Q_LINE("table_index",tabIndex,0,0,"integer");
      INT totalShift = quantizershift - accuShift + 1;
      Q_LINE("exponent_index",totalShift&3,0,0,"integer");
      accu = fMultDiv2(FDKaacEnc_mTab_3_4[tabIndex],
                       FDKaacEnc_quantTableE[totalShift & 3]);
      Q_LINE("mul_e",accu,31,0,"internal");
      totalShift = (16 - 4) - (3 * (totalShift >> 2));
      Q_LINE("right_shift",fixMin(totalShift,DFRACT_BITS-1),0,0,"integer");
      FDK_ASSERT(totalShift >= 0); /* MAX_QUANT_VIOLATION */
      accu >>= fixMin(totalShift, DFRACT_BITS - 1);
      Q_LINE("shifted",accu,31,0,"internal");
      quaSpectrum[line] =
          (SHORT)(-((LONG)(k + accu) >> (DFRACT_BITS - 1 - 16)));
    } else if (accu > FL2FXCONST_DBL(0.0f)) {
      /* normalize */
      INT accuShift = CntLeadingZeros(accu) - 1; /* CountLeadingBits() is not
                                                    necessary here since test
                                                    value is always > 0 */
      accu <<= accuShift;
      Q_LINE("clz",accuShift,0,0,"integer");
      Q_LINE("normalized",accu,31,0,"internal");
      INT tabIndex =
          (INT)(accu >> (DFRACT_BITS - 2 - MANT_DIGITS)) & (~MANT_SIZE);
      Q_LINE("table_index",tabIndex,0,0,"integer");
      INT totalShift = quantizershift - accuShift + 1;
      Q_LINE("exponent_index",totalShift&3,0,0,"integer");
      accu = fMultDiv2(FDKaacEnc_mTab_3_4[tabIndex],
                       FDKaacEnc_quantTableE[totalShift & 3]);
      Q_LINE("mul_e",accu,31,0,"internal");
      totalShift = (16 - 4) - (3 * (totalShift >> 2));
      Q_LINE("right_shift",fixMin(totalShift,DFRACT_BITS-1),0,0,"integer");
      FDK_ASSERT(totalShift >= 0); /* MAX_QUANT_VIOLATION */
      accu >>= fixMin(totalShift, DFRACT_BITS - 1);
      Q_LINE("shifted",accu,31,0,"internal");
      quaSpectrum[line] = (SHORT)((LONG)(k + accu) >> (DFRACT_BITS - 1 - 16));
    } else {
      quaSpectrum[line] = 0;
    }
    Q_LINE("quantized",quaSpectrum[line],0,0,"quantized_integer");
  }
}

/*****************************************************************************

    functionname:iFDKaacEnc_quantizeLines
    description: iquantizes spectrum lines
                 mdctSpectrum = iquaSpectrum^4/3 *2^(0.25*gain)
    input: global gain, number of lines to process,quantized spectrum
    output: spectral data

*****************************************************************************/
static void FDKaacEnc_invQuantizeLines(INT gain, INT noOfLines,
                                       SHORT *quantSpectrum,
                                       FIXP_DBL *mdctSpectrum)

{
  INT iquantizermod;
  INT iquantizershift;
  INT line;

  iquantizermod = gain & 3;
  iquantizershift = gain >> 2;

  for (line = 0; line < noOfLines; line++) {
    if (quantSpectrum[line] < 0) {
      FIXP_DBL accu;
      INT ex, specExp, tabIndex;
      FIXP_DBL s, t;

      accu = (FIXP_DBL)-quantSpectrum[line];

      ex = CountLeadingBits(accu);
      accu <<= ex;
      specExp = (DFRACT_BITS - 1) - ex;

      FDK_ASSERT(specExp < 14); /* this fails if abs(value) > 8191 */

      tabIndex = (INT)(accu >> (DFRACT_BITS - 2 - MANT_DIGITS)) & (~MANT_SIZE);

      /* calculate "mantissa" ^4/3 */
      s = FDKaacEnc_mTab_4_3Elc[tabIndex];

      /* get approperiate exponent multiplier for specExp^3/4 combined with
       * scfMod */
      t = FDKaacEnc_specExpMantTableCombElc[iquantizermod][specExp];

      /* multiply "mantissa" ^4/3 with exponent multiplier */
      accu = fMult(s, t);

      /* get approperiate exponent shifter */
      specExp = FDKaacEnc_specExpTableComb[iquantizermod][specExp] -
                1; /* -1 to avoid overflows in accu */

      if ((-iquantizershift - specExp) < 0)
        accu <<= -(-iquantizershift - specExp);
      else
        accu >>= -iquantizershift - specExp;

      mdctSpectrum[line] = -accu;
    } else if (quantSpectrum[line] > 0) {
      FIXP_DBL accu;
      INT ex, specExp, tabIndex;
      FIXP_DBL s, t;

      accu = (FIXP_DBL)(INT)quantSpectrum[line];

      ex = CountLeadingBits(accu);
      accu <<= ex;
      specExp = (DFRACT_BITS - 1) - ex;

      FDK_ASSERT(specExp < 14); /* this fails if abs(value) > 8191 */

      tabIndex = (INT)(accu >> (DFRACT_BITS - 2 - MANT_DIGITS)) & (~MANT_SIZE);

      /* calculate "mantissa" ^4/3 */
      s = FDKaacEnc_mTab_4_3Elc[tabIndex];

      /* get approperiate exponent multiplier for specExp^3/4 combined with
       * scfMod */
      t = FDKaacEnc_specExpMantTableCombElc[iquantizermod][specExp];

      /* multiply "mantissa" ^4/3 with exponent multiplier */
      accu = fMult(s, t);

      /* get approperiate exponent shifter */
      specExp = FDKaacEnc_specExpTableComb[iquantizermod][specExp] -
                1; /* -1 to avoid overflows in accu */

      if ((-iquantizershift - specExp) < 0)
        accu <<= -(-iquantizershift - specExp);
      else
        accu >>= -iquantizershift - specExp;

      mdctSpectrum[line] = accu;
    } else {
      mdctSpectrum[line] = FL2FXCONST_DBL(0.0f);
    }
  }
}

/*****************************************************************************

    functionname: FDKaacEnc_QuantizeSpectrum
    description: quantizes the entire spectrum
    returns:
    input: number of scalefactor bands to be quantized, ...
    output: quantized spectrum

*****************************************************************************/
void FDKaacEnc_QuantizeSpectrum(INT sfbCnt, INT maxSfbPerGroup, INT sfbPerGroup,
                                const INT *sfbOffset,
                                const FIXP_DBL *mdctSpectrum, INT globalGain,
                                const INT *scalefactors,
                                 SHORT *quantizedSpectrum,
                                 INT dZoneQuantEnable) {
  QV("global_gain","rate",globalGain);
  QV("quantization","dead_zone",dZoneQuantEnable);
  INT sfbOffs, sfb;

  FDK_ENC_PROFILE_COUNTER_ADD(FDK_ENC_PROFILE_COUNTER_QMAX_SCANS, 1);

  /* in FDKaacEnc_quantizeLines quaSpectrum is calculated with:
        spec^(3/4) * 2^(-3/16*QSS) * 2^(3/4*scale) + k
     simplify scaling calculation and reduce QSS before:
        spec^(3/4) * 2^(-3/16*(QSS - 4*scale)) */

  for (sfbOffs = 0; sfbOffs < sfbCnt; sfbOffs += sfbPerGroup) {
    for (sfb = 0; sfb < maxSfbPerGroup; sfb++) {
      INT scalefactor = scalefactors[sfbOffs + sfb];
      const INT noOfLines =
          sfbOffset[sfbOffs + sfb + 1] - sfbOffset[sfbOffs + sfb];

      FDK_ENC_PROFILE_COUNTER_ADD(FDK_ENC_PROFILE_COUNTER_QMAX_LINES,
                                  noOfLines);

      FDKaacEnc_quantizeLines(
          globalGain - scalefactor, /* QSS */
          noOfLines,
          mdctSpectrum + sfbOffset[sfbOffs + sfb],
          quantizedSpectrum + sfbOffset[sfbOffs + sfb], dZoneQuantEnable);
    }
  }
}

/*****************************************************************************

    functionname: FDKaacEnc_calcSfbDist
    description: calculates distortion of quantized values
    returns: distortion
    input: gain, number of lines to process, spectral data
    output:

*****************************************************************************/
FIXP_DBL FDKaacEnc_calcSfbDist(const FIXP_DBL *mdctSpectrum,
                               SHORT *quantSpectrum, INT noOfLines, INT gain,
                               INT dZoneQuantEnable) {
  FDK_ENC_PROFILE_SCOPE(calcSfbDistProfile,
                        FDK_ENC_PROFILE_CALC_SFB_DIST);
  INT i, scale;
  FIXP_DBL xfsf;
  FIXP_DBL diff;
  FIXP_DBL invQuantSpec;

  xfsf = FL2FXCONST_DBL(0.0f);

  for (i = 0; i < noOfLines; i++) {
    /* quantization */
    FDKaacEnc_quantizeLines(gain, 1, &mdctSpectrum[i], &quantSpectrum[i],
                            dZoneQuantEnable);

    if (fAbs(quantSpectrum[i]) > MAX_QUANT) {
      QUANT_OBSERVE(FDKquantDebugTrialCount(i+1));
      QV("iterations","trial.range_violation",1);
      return FL2FXCONST_DBL(0.0f);
    }
    /* inverse quantization */
    FDKaacEnc_invQuantizeLines(gain, 1, &quantSpectrum[i], &invQuantSpec);
    Q_LINE("inverse",invQuantSpec,31,FDKquantDebugScale()+1,"pcm");

    /* dist */
    diff = fixp_abs(fixp_abs(invQuantSpec) - fixp_abs(mdctSpectrum[i] >> 1));
    Q_LINE("difference_half_scale",diff,31,FDKquantDebugScale()+1,"pcm");

    scale = CountLeadingBits(diff);
    diff = scaleValue(diff, scale);
    diff = fPow2(diff);
    scale = fixMin(2 * (scale - 1), DFRACT_BITS - 1);

    diff = scaleValue(diff, -scale);

    xfsf = xfsf + diff;
  }

  xfsf = CalcLdData(xfsf);

  return xfsf;
}

#ifdef QUANT_DEBUG
void FDKquantDebugReconstructAccepted(const PSY_OUT_CHANNEL *p,const QC_OUT_CHANNEL *q) {
  if(!FDKquantDebugSelected())return;
  FIXP_DBL reconstructed[1024]={0};
  SHORT copy[1024]={0};
  for(int base=0;base<p->sfbCnt;base+=p->sfbPerGroup)for(int band=0;band<p->maxSfbPerGroup;band++) {
    int b=base+band,start=p->sfbOffsets[b],stop=p->sfbOffsets[b+1];
    for(int line=start;line<stop;line++)copy[line]=q->quantSpec[line];
    FDKaacEnc_invQuantizeLines(q->globalGain-q->scf[b],stop-start,copy+start,reconstructed+start);
  }
  QUANT_OBSERVE(FDKquantDebugDbl("final","reconstructed_spectrum",reconstructed,1024,p->mdctScale+1,"pcm",0,QD_SPECTRUM));
}
#endif

/*****************************************************************************

    functionname: FDKaacEnc_calcSfbQuantEnergyAndDist
    description: calculates energy and distortion of quantized values
    returns:
    input: gain, number of lines to process, quantized spectral data,
           spectral data
    output: energy, distortion

*****************************************************************************/
void FDKaacEnc_calcSfbQuantEnergyAndDist(FIXP_DBL *mdctSpectrum,
                                         SHORT *quantSpectrum, INT noOfLines,
                                         INT gain, FIXP_DBL *en,
                                         FIXP_DBL *dist) {
  FDK_ENC_PROFILE_SCOPE(quantEnergyDistProfile,
                        FDK_ENC_PROFILE_CALC_SFB_QUANT_ENERGY_DIST);
  QUANT_OBSERVE(FDKquantDebugRange(mdctSpectrum,noOfLines,gain,0));
  Q_SCOPE("scalefactor","rescale_trial",-1,FDKquantDebugTrial(FDKquantDebugSfb()),FDKquantDebugSfb());
  QUANT_OBSERVE(FDKquantDebugShort("scalefactor","rescale.quantized_input",quantSpectrum,noOfLines,FDKquantDebugSfb()));
  FDK_ENC_PROFILE_COUNTER_ADD(FDK_ENC_PROFILE_COUNTER_QUANT_ENERGY_CALLS, 1);
  FDK_ENC_PROFILE_COUNTER_ADD(FDK_ENC_PROFILE_COUNTER_QUANT_ENERGY_LINES,
                              noOfLines);
  INT i, scale;
  FIXP_DBL invQuantSpec;
  FIXP_DBL diff;

  FIXP_DBL energy = FL2FXCONST_DBL(0.0f);
  FIXP_DBL distortion = FL2FXCONST_DBL(0.0f);

  for (i = 0; i < noOfLines; i++) {
    if (fAbs(quantSpectrum[i]) > MAX_QUANT) {
      *en = FL2FXCONST_DBL(0.0f);
      *dist = FL2FXCONST_DBL(0.0f);
      return;
    }

    /* inverse quantization */
    FDKaacEnc_invQuantizeLines(gain, 1, &quantSpectrum[i], &invQuantSpec);

    /* energy */
    energy += fPow2(invQuantSpec);

    /* dist */
    diff = fixp_abs(fixp_abs(invQuantSpec) - fixp_abs(mdctSpectrum[i] >> 1));

    scale = CountLeadingBits(diff);
    diff = scaleValue(diff, scale);
    diff = fPow2(diff);

    scale = fixMin(2 * (scale - 1), DFRACT_BITS - 1);

    diff = scaleValue(diff, -scale);

    distortion += diff;
  }

  *en = CalcLdData(energy) + FL2FXCONST_DBL(0.03125f);
  *dist = CalcLdData(distortion);
  QV("iterations","rescale.gain",gain);
  QUANT_OBSERVE(FDKquantDebugScalar("iterations","rescale.energy_ld",*en,32,31,2*FDKquantDebugScale(),"ld64"));
  QUANT_OBSERVE(FDKquantDebugScalar("iterations","rescale.distortion_ld",*dist,32,31,2*FDKquantDebugScale(),"ld64"));
}
