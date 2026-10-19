-------------------------------------------------------------------------------
-- One-window masking engine after the TNS boundary.
-- Native order: clipping, bidirectional max-spreading, PCM floor, pre-echo,
-- energy spreading, threshold log. History is explicit: the future element
-- scheduler owns context storage and supplies the next window's history.
-- pcm_shift is the native energyShift AFTER adding PCM_QUANT_THR_SCALE for
-- this window; the caller must preserve the native short-window recurrence.
-- New implementation, 2026-10-17. FDK-derived arithmetic; see repository NOTICE.
-------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.psy_pkg.all;

entity psy_masking is
  port (
    clk, rst_n : in std_logic;
    cmd_valid : in std_logic;
    cmd_ready : out std_logic;
    cmd_bands : in natural range 0 to PSY_MAX_BANDS;
    cmd_block : in unsigned(1 downto 0);
    cmd_scale : in integer range -3 to 31;
    cmd_pcm_shift : in integer range -64 to 256;
    cmd_is_lfe : in std_logic;
    cfg_clip : in psy_word_t;
    cfg_mask_low, cfg_mask_high : in psy_band_words_t;
    cfg_spread_low, cfg_spread_high : in psy_band_words_t;
    cfg_pcm_floor : in psy_band_words_t;
    cfg_min_remaining : in psy_half_t;
    energy_i, threshold_i, history_i : in psy_band_words_t;
    history_scale_i : in integer range -3 to 31;
    history_calc_i : in std_logic;
    out_valid : out std_logic;
    out_ready : in std_logic;
    out_status : out unsigned(3 downto 0);
    threshold_o, threshold_ld_o, spread_energy_o, history_o : out psy_band_words_t;
    history_scale_o : out integer range -3 to 31;
    history_calc_o : out std_logic
  );
end entity;

architecture rtl of psy_masking is
  type state_t is (IDLE, CLIP, SPREAD_UP, SPREAD_DOWN, PCM_AND_PRE_ECHO,
    ENERGY_UP, ENERGY_DOWN, LOG_SEND, LOG_WAIT, OUTPUT_RESULT);
  signal state : state_t := IDLE;
  signal threshold, threshold_ld, spread, history : psy_band_words_t;
  signal mask_low, mask_high, spread_low, spread_high, pcm_floor : psy_band_words_t;
  signal bands : natural range 1 to PSY_MAX_BANDS := 1;
  signal index : natural range 0 to PSY_MAX_BANDS-1 := 0;
  signal block_type : unsigned(1 downto 0) := "00";
  signal scale, previous_scale : integer range -3 to 31 := 0;
  signal pcm_shift : integer range -64 to 256 := 0;
  signal clip_value : psy_word_t := PSY_ZERO;
  signal remaining : psy_half_t := x"0148";
  signal calc, lfe : std_logic := '0';
  signal status : unsigned(3 downto 0) := PSY_OK;
  signal output_history_scale : integer range -3 to 31 := 0;
  signal output_calc : std_logic := '0';
  signal log_in_valid, log_in_ready, log_out_valid : std_logic;
  signal log_input, log_out : psy_word_t;
begin
  cmd_ready<='1' when state=IDLE and rst_n='1' else '0';
  out_valid<='1' when state=OUTPUT_RESULT and rst_n='1' else '0';
  out_status<=status;
  threshold_o<=threshold; threshold_ld_o<=threshold_ld;
  spread_energy_o<=spread; history_o<=history;
  history_scale_o<=output_history_scale; history_calc_o<=output_calc;
  log_in_valid<='1' when state=LOG_SEND else '0';
  log_input<=threshold(index);
  u_log : entity work.psy_log2
    port map(clk,rst_n,log_in_valid,log_in_ready,log_input,
             log_out_valid,'1',log_out);
  process(clk)
    variable raw, limited, previous_limit, minimum_keep, floor_value : psy_word_t;
    variable difference, clip_shift, allowed_headroom : integer;
    variable invalid : boolean;
  begin
    if rising_edge(clk) then
      if rst_n='0' then
        state<=IDLE; index<=0; status<=PSY_OK;
      else
        case state is
          when IDLE =>
            if cmd_valid='1' then
              invalid:=cmd_bands=0 or cfg_clip<PSY_ZERO or cfg_min_remaining<0;
              for b in 0 to PSY_MAX_BANDS-1 loop
                if b<cmd_bands then
                  invalid:=invalid or threshold_i(b)<PSY_ZERO or energy_i(b)<PSY_ZERO
                    or history_i(b)<PSY_ZERO or cfg_pcm_floor(b)<PSY_ZERO
                    or cfg_mask_low(b)<PSY_ZERO or cfg_mask_high(b)<PSY_ZERO
                    or cfg_spread_low(b)<PSY_ZERO or cfg_spread_high(b)<PSY_ZERO;
                end if;
              end loop;
              threshold<=threshold_i; spread<=energy_i; history<=history_i;
              output_history_scale<=history_scale_i; output_calc<=history_calc_i;
              status<=PSY_OK;
              if invalid then status<=PSY_BAD_CONFIG; state<=OUTPUT_RESULT;
              elsif cmd_is_lfe='0' and cmd_block/="11" and history_calc_i='1'
                    and abs(cmd_scale-history_scale_i)>15 then
                status<=PSY_BAD_SCALE; state<=OUTPUT_RESULT;
              else
                bands<=cmd_bands; block_type<=cmd_block; scale<=cmd_scale;
                pcm_shift<=cmd_pcm_shift; lfe<=cmd_is_lfe; remaining<=cfg_min_remaining;
                mask_low<=cfg_mask_low; mask_high<=cfg_mask_high;
                spread_low<=cfg_spread_low; spread_high<=cfg_spread_high;
                pcm_floor<=cfg_pcm_floor; calc<=history_calc_i; previous_scale<=history_scale_i;
                if cmd_is_lfe='0' and cmd_block="11" then calc<='0'; end if;
                clip_shift:=2*cmd_scale-4;
                allowed_headroom:=0;
                if cmd_block="10" then allowed_headroom:=6; end if;
                if clip_shift>=0 then clip_value<=shift_right(cfg_clip,clip_shift);
                elsif clip_shift>=-allowed_headroom then clip_value<=shift_left(cfg_clip,-clip_shift);
                else clip_value<=PSY_WORD_MAX; end if;
                index<=0; state<=CLIP;
              end if;
            end if;
          when CLIP =>
            threshold(index)<=psy_min(threshold(index),clip_value);
            if index+1<bands then index<=index+1;
            elsif bands=1 then index<=0; state<=PCM_AND_PRE_ECHO;
            else index<=1; state<=SPREAD_UP; end if;
          when SPREAD_UP =>
            threshold(index)<=psy_max(threshold(index),psy_mul(mask_high(index),threshold(index-1)));
            if index+1<bands then index<=index+1;
            else index<=bands-2; state<=SPREAD_DOWN; end if;
          when SPREAD_DOWN =>
            threshold(index)<=psy_max(threshold(index),psy_mul(mask_low(index),threshold(index+1)));
            if index>0 then index<=index-1;
            else state<=PCM_AND_PRE_ECHO; end if;
          when PCM_AND_PRE_ECHO =>
            floor_value:=psy_scale(pcm_floor(index),-psy_minimum(31,abs(pcm_shift)));
            if pcm_shift<0 then floor_value:=psy_scale(pcm_floor(index),psy_minimum(31,-pcm_shift)); end if;
            raw:=psy_max(shift_right(threshold(index),4),floor_value);
            limited:=raw;
            if lfe='0' then
              if calc='1' then
                minimum_keep:=psy_mul_ds(raw,remaining);
                if scale>previous_scale then
                  difference:=2*(scale-previous_scale);
                  previous_limit:=shift_left(shift_right(history(index),difference),1);
                  limited:=psy_max(psy_min(raw,previous_limit),minimum_keep);
                else
                  difference:=2*(previous_scale-scale);
                  previous_limit:=history(index);
                  if shift_right(raw,difference+1)>previous_limit then
                    limited:=shift_left(previous_limit,difference+1);
                  end if;
                  limited:=psy_max(limited,minimum_keep);
                end if;
              end if;
              history(index)<=raw;
              output_history_scale<=scale; output_calc<='1';
              if block_type="01" then
                history(index)<=PSY_WORD_MAX; output_history_scale<=0; output_calc<='0';
              end if;
            end if;
            threshold(index)<=limited;
            if index+1<bands then index<=index+1;
            elsif bands=1 then index<=0; state<=LOG_SEND;
            else index<=1; state<=ENERGY_UP; end if;
          when ENERGY_UP =>
            spread(index)<=psy_max(spread(index),psy_mul(spread_high(index),spread(index-1)));
            if index+1<bands then index<=index+1;
            else index<=bands-2; state<=ENERGY_DOWN; end if;
          when ENERGY_DOWN =>
            spread(index)<=psy_max(spread(index),psy_mul(spread_low(index),spread(index+1)));
            if index>0 then index<=index-1;
            else state<=LOG_SEND; end if;
          when LOG_SEND =>
            if log_in_ready='1' then state<=LOG_WAIT; end if;
          when LOG_WAIT =>
            if log_out_valid='1' then
              threshold_ld(index)<=psy_max(log_out,PSY_LD_FLOOR);
              if index+1<bands then index<=index+1; state<=LOG_SEND;
              else state<=OUTPUT_RESULT; end if;
            end if;
          when OUTPUT_RESULT =>
            if out_ready='1' then state<=IDLE; end if;
        end case;
      end if;
    end if;
  end process;
end architecture;
