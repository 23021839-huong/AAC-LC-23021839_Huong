-------------------------------------------------------------------------------
-- Spectrum -> low-pass -> per-SFB headroom/energy/log -> global rescaling.
-- This is a checkpoint-producing FRONTEND, not a complete PSY_OUT producer.
-- TNS, tonality, masking, PNS, grouping and stereo decisions are not bypassed
-- or claimed here. Integrate those stages before connecting this design to QC.
-- New implementation, 2026-10-17. FDK-derived arithmetic; see repository NOTICE.
-------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.psy_pkg.all;

entity psy_sfb_frontend is
  port (
    clk, rst_n : in std_logic;
    cmd_valid : in std_logic;
    cmd_ready : out std_logic;
    cmd_short : in std_logic;
    cmd_channels : in natural range 1 to 2;
    cmd_mdct_scale : in integer range 0 to 31;
    cfg_bands : in natural range 0 to PSY_MAX_BANDS;
    cfg_lowpass : in natural range 0 to PSY_FRAME_LEN;
    cfg_offsets : in psy_offsets_t;
    -- Exactly 1024 words/channel; channel-major, natural transform order.
    in_valid : in std_logic;
    in_ready : out std_logic;
    in_data : in psy_word_t;
    spec_valid : out std_logic;
    spec_ready : in std_logic;
    spec_channel : out natural range 0 to 1;
    spec_index : out natural range 0 to PSY_FRAME_LEN-1;
    spec_data : out psy_word_t;
    band_valid : out std_logic;
    band_ready : in std_logic;
    band_channel : out natural range 0 to 1;
    band_window : out natural range 0 to 7;
    band_index : out natural range 0 to PSY_MAX_BANDS-1;
    band_headroom : out natural range 0 to 30;
    band_energy, band_energy_ld, band_threshold : out psy_word_t;
    result_valid : out std_logic;
    result_ready : in std_logic;
    result_status : out unsigned(3 downto 0);
    result_scale : out integer range -3 to 31;
    result_shift : out natural range 0 to 30;
    result_zero : out std_logic;
    busy : out std_logic
  );
end entity;

architecture rtl of psy_sfb_frontend is
  type state_t is (IDLE, LOAD, CHECK_INPUT, HEAD_INIT, HEAD_READ, HEAD_USE,
    ENERGY_INIT, ENERGY_READ, ENERGY_USE, LOG_SEND, LOG_WAIT, NEXT_ENERGY,
    WINDOW_MAX, SELECT_SHIFT, ADJUST_BANDS, SCALE_READ, SCALE_WRITE,
    ZERO_BANDS, SPEC_READ, SPEC_OUTPUT, BAND_OUTPUT, RESULT_OUTPUT);
  signal state : state_t := IDLE;
  type spectrum_t is array(0 to 2047) of psy_word_t;
  type headrooms_t is array(0 to PSY_MAX_SLOTS-1) of natural range 0 to 30;
  signal spectrum : spectrum_t;
  signal energies, logs, thresholds : psy_words_t(0 to PSY_MAX_SLOTS-1);
  signal headrooms : headrooms_t;
  signal offsets : psy_offsets_t;
  signal short_block : std_logic := '0';
  signal channels : natural range 1 to 2 := 1;
  signal bands : natural range 1 to PSY_MAX_BANDS := 1;
  signal windows : natural range 1 to 8 := 1;
  signal window_length : natural range 128 to 1024 := 1024;
  signal lowpass : natural range 0 to 1024 := 0;
  signal mdct_scale : integer range 0 to 31 := 0;
  signal channel : natural range 0 to 1 := 0;
  signal win : natural range 0 to 7 := 0;
  signal band : natural range 0 to PSY_MAX_BANDS-1 := 0;
  signal line_index : natural range 0 to 1023 := 0;
  signal transfer_index : natural range 0 to 2047 := 0;
  signal sample, max_sample, sum_energy, max_energy, window_max_log : psy_word_t := PSY_ZERO;
  signal zero_spectrum : std_logic := '1';
  signal status : unsigned(3 downto 0) := PSY_OK;
  signal minimum_shift : natural range 0 to 31 := 31;
  signal final_shift : natural range 0 to 30 := 0;
  signal output_scale : integer range -3 to 31 := 0;
  signal window_max_band : natural range 0 to PSY_MAX_BANDS-1 := 0;
  signal log_in_valid, log_in_ready, log_out_valid : std_logic;
  signal log_out : psy_word_t;
begin
  cmd_ready<='1' when state=IDLE and rst_n='1' else '0';
  in_ready<='1' when state=LOAD and rst_n='1' else '0';
  spec_valid<='1' when state=SPEC_OUTPUT and rst_n='1' else '0';
  spec_channel<=transfer_index/1024;
  spec_index<=transfer_index mod 1024;
  spec_data<=sample;
  band_valid<='1' when state=BAND_OUTPUT and rst_n='1' else '0';
  band_channel<=channel; band_window<=win; band_index<=band;
  band_headroom<=headrooms(psy_slot(channel,win,band,short_block));
  band_energy<=energies(psy_slot(channel,win,band,short_block));
  band_energy_ld<=logs(psy_slot(channel,win,band,short_block));
  band_threshold<=thresholds(psy_slot(channel,win,band,short_block));
  result_valid<='1' when state=RESULT_OUTPUT and rst_n='1' else '0';
  result_status<=status; result_scale<=output_scale;
  result_shift<=final_shift; result_zero<=zero_spectrum;
  busy<='0' when state=IDLE else '1';
  log_in_valid<='1' when state=LOG_SEND else '0';
  u_log : entity work.psy_log2
    port map(clk,rst_n,log_in_valid,log_in_ready,shift_left(sum_energy,1),
             log_out_valid,'1',log_out);

  process(clk)
    variable value, magnitude, local_energy, corrected_log, scaled_energy : psy_word_t;
    variable local_shift, shift_amount, nrg_shift, selected : integer;
    variable slot, hr, address : natural;
    variable valid_config : boolean;
  begin
    if rising_edge(clk) then
      if rst_n='0' then
        state<=IDLE; status<=PSY_OK; final_shift<=0; output_scale<=0;
        channel<=0; win<=0; band<=0; transfer_index<=0; sample<=PSY_ZERO;
      else
        slot:=psy_slot(channel,win,band,short_block);
        case state is
          when IDLE =>
            if cmd_valid='1' then
              valid_config:=psy_valid_offsets(cfg_offsets,cfg_bands,1024);
              if cmd_short='1' then
                valid_config:=psy_valid_offsets(cfg_offsets,cfg_bands,128)
                  and cfg_bands<=15 and cfg_lowpass<=128;
              end if;
              if cfg_bands>0 then
                valid_config:=valid_config and cfg_offsets(cfg_bands)>=cfg_lowpass;
              end if;
              status<=PSY_OK; final_shift<=0; output_scale<=cmd_mdct_scale;
              zero_spectrum<='1'; transfer_index<=0; channel<=0; win<=0; band<=0;
              if not valid_config then
                status<=PSY_BAD_CONFIG; state<=RESULT_OUTPUT;
              else
                offsets<=cfg_offsets; bands<=cfg_bands; lowpass<=cfg_lowpass;
                channels<=cmd_channels; mdct_scale<=cmd_mdct_scale; short_block<=cmd_short;
                if cmd_short='1' then windows<=8; window_length<=128;
                else windows<=1; window_length<=1024; end if;
                state<=LOAD;
              end if;
            end if;
          when LOAD =>
            if in_valid='1' then
              value:=in_data;
              if (transfer_index mod window_length)>=lowpass then value:=PSY_ZERO; end if;
              spectrum(transfer_index)<=value;
              -- Native abs(INT_MIN) is not a portable positive magnitude.
              -- Reject it instead of silently claiming native bit equivalence.
              if value=PSY_WORD_MIN then status<=PSY_BAD_SAMPLE; end if;
              if value/=PSY_ZERO then zero_spectrum<='0'; end if;
              if transfer_index=channels*1024-1 then state<=CHECK_INPUT;
              else transfer_index<=transfer_index+1; end if;
            end if;
          when CHECK_INPUT =>
            minimum_shift<=31; max_energy<=PSY_ZERO;
            if status/=PSY_OK then state<=RESULT_OUTPUT;
            elsif zero_spectrum='1' then output_scale<=0; state<=ZERO_BANDS;
            else state<=HEAD_INIT; end if;
          when HEAD_INIT =>
            max_sample<=PSY_ZERO; line_index<=offsets(band); state<=HEAD_READ;
          when HEAD_READ =>
            sample<=spectrum(channel*1024+win*window_length+line_index);
            state<=HEAD_USE;
          when HEAD_USE =>
            magnitude:=psy_abs(sample); value:=psy_max(max_sample,magnitude);
            max_sample<=value;
            if line_index=offsets(band+1)-1 then
              hr:=psy_minimum(30,psy_clz(value)-1);
              headrooms(slot)<=hr;
              minimum_shift<=psy_minimum(minimum_shift,hr);
              if band+1<bands then band<=band+1; state<=HEAD_INIT;
              elsif win+1<windows then band<=0; win<=win+1; state<=HEAD_INIT;
              elsif channel+1<channels then band<=0; win<=0; channel<=channel+1; state<=HEAD_INIT;
              else channel<=0; win<=0; band<=0; window_max_log<=PSY_WORD_MIN;
                window_max_band<=0; state<=ENERGY_INIT;
              end if;
            else line_index<=line_index+1; state<=HEAD_READ; end if;
          when ENERGY_INIT =>
            sum_energy<=PSY_ZERO; line_index<=offsets(band); state<=ENERGY_READ;
          when ENERGY_READ =>
            sample<=spectrum(channel*1024+win*window_length+line_index);
            state<=ENERGY_USE;
          when ENERGY_USE =>
            local_shift:=psy_maximum(0,integer(headrooms(slot))-4);
            value:=psy_scale(sample,local_shift);
            sum_energy<=sum_energy+psy_mul_div2(value,value);
            if line_index=offsets(band+1)-1 then state<=LOG_SEND;
            else line_index<=line_index+1; state<=ENERGY_READ; end if;
          when LOG_SEND =>
            if log_in_ready='1' then state<=LOG_WAIT; end if;
          when LOG_WAIT =>
            if log_out_valid='1' then
              local_energy:=shift_left(sum_energy,1);
              local_shift:=psy_maximum(0,integer(headrooms(slot))-4);
              corrected_log:=log_out;
              if log_out/=PSY_WORD_MIN then
                corrected_log:=log_out-to_signed(local_shift*67108864,32);
              end if;
              energies(slot)<=local_energy; logs(slot)<=corrected_log;
              if corrected_log>window_max_log then
                window_max_log<=corrected_log; window_max_band<=band;
              end if;
              state<=NEXT_ENERGY;
            end if;
          when NEXT_ENERGY =>
            if band+1<bands then band<=band+1; state<=ENERGY_INIT;
            else state<=WINDOW_MAX; end if;
          when WINDOW_MAX =>
            address:=psy_slot(channel,win,window_max_band,short_block);
            local_shift:=psy_maximum(0,integer(headrooms(address))-4);
            shift_amount:=psy_maximum(2*(integer(minimum_shift)-4-local_shift),-31);
            max_energy<=psy_max(max_energy,psy_scale(energies(address),shift_amount));
            window_max_log<=PSY_WORD_MIN; window_max_band<=0; band<=0;
            if win+1<windows then win<=win+1; state<=ENERGY_INIT;
            elsif channel+1<channels then win<=0; channel<=channel+1; state<=ENERGY_INIT;
            else channel<=0; win<=0; state<=SELECT_SHIFT; end if;
          when SELECT_SHIFT =>
            nrg_shift:=31;
            if max_energy/=PSY_ZERO then
              nrg_shift:=integer(psy_norm(max_energy))/2+integer(minimum_shift)-4;
            end if;
            if short_block='1' then nrg_shift:=nrg_shift-1; end if;
            selected:=psy_minimum(psy_minimum(minimum_shift,nrg_shift),mdct_scale+3);
            if selected<0 or selected>30 then
              status<=PSY_BAD_SCALE; state<=RESULT_OUTPUT;
            else
              final_shift<=selected; output_scale<=mdct_scale-selected; state<=ADJUST_BANDS;
            end if;
          when ADJUST_BANDS =>
            local_shift:=psy_maximum(0,integer(headrooms(slot))-4);
            shift_amount:=psy_minimum(2*(local_shift-integer(final_shift)),31);
            scaled_energy:=psy_scale(energies(slot),-shift_amount);
            energies(slot)<=scaled_energy;
            thresholds(slot)<=psy_mul(scaled_energy,PSY_C_RATIO);
            logs(slot)<=logs(slot)+to_signed(final_shift*67108864,32);
            headrooms(slot)<=headrooms(slot)-final_shift;
            if band+1<bands then band<=band+1;
            elsif win+1<windows then band<=0; win<=win+1;
            elsif channel+1<channels then band<=0; win<=0; channel<=channel+1;
            else channel<=0; win<=0; band<=0; transfer_index<=0; state<=SCALE_READ; end if;
          when SCALE_READ =>
            sample<=spectrum(transfer_index); state<=SCALE_WRITE;
          when SCALE_WRITE =>
            spectrum(transfer_index)<=psy_scale(sample,final_shift);
            if transfer_index=channels*1024-1 then transfer_index<=0; state<=SPEC_READ;
            else transfer_index<=transfer_index+1; state<=SCALE_READ; end if;
          when ZERO_BANDS =>
            headrooms(slot)<=0; energies(slot)<=PSY_ZERO;
            logs(slot)<=PSY_WORD_MIN; thresholds(slot)<=PSY_ZERO;
            if band+1<bands then band<=band+1;
            elsif win+1<windows then band<=0; win<=win+1;
            elsif channel+1<channels then band<=0; win<=0; channel<=channel+1;
            else channel<=0; win<=0; band<=0; transfer_index<=0; state<=SPEC_READ; end if;
          when SPEC_READ =>
            sample<=spectrum(transfer_index); state<=SPEC_OUTPUT;
          when SPEC_OUTPUT =>
            if spec_ready='1' then
              if transfer_index=channels*1024-1 then state<=BAND_OUTPUT;
              else transfer_index<=transfer_index+1; state<=SPEC_READ; end if;
            end if;
          when BAND_OUTPUT =>
            if band_ready='1' then
              if band+1<bands then band<=band+1;
              elsif win+1<windows then band<=0; win<=win+1;
              elsif channel+1<channels then band<=0; win<=0; channel<=channel+1;
              else state<=RESULT_OUTPUT; end if;
            end if;
          when RESULT_OUTPUT =>
            if result_ready='1' then state<=IDLE; end if;
        end case;
      end if;
    end if;
  end process;
end architecture;
