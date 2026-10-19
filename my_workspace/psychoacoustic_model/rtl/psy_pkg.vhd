-------------------------------------------------------------------------------
-- New implementation, 2026-10-17. FDK-derived arithmetic; see repository NOTICE.
-- Numerical profile: generic DD/DS multiplication, LDCOEFF_16BIT, AAC-LC 1024.
-- This package does not contain MDCT or quantization/coding functionality.
-------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

package psy_pkg is
  constant PSY_FRAME_LEN : positive := 1024;
  constant PSY_SHORT_LEN : positive := 128;
  constant PSY_MAX_BANDS : positive := 51;
  constant PSY_SHORT_BANDS : positive := 15;
  constant PSY_WINDOW_SLOTS : positive := 120;
  constant PSY_MAX_SLOTS : positive := 240;
  subtype psy_word_t is signed(31 downto 0);
  subtype psy_half_t is signed(15 downto 0);
  type psy_words_t is array(natural range <>) of psy_word_t;
  type psy_naturals_t is array(natural range <>) of natural range 0 to 1024;
  subtype psy_offsets_t is psy_naturals_t(0 to PSY_MAX_BANDS);
  subtype psy_band_words_t is psy_words_t(0 to PSY_MAX_BANDS-1);
  constant PSY_ZERO : psy_word_t := x"00000000";
  constant PSY_WORD_MAX : psy_word_t := x"7FFFFFFF";
  constant PSY_WORD_MIN : psy_word_t := x"80000000";
  constant PSY_C_RATIO : psy_word_t := x"02940A10";
  constant PSY_LD_STEP : psy_word_t := x"04000000"; -- 2/64 in Q31
  constant PSY_LD_FLOOR : psy_word_t := x"BE000000"; -- -33/64 in Q31
  constant PSY_OK : unsigned(3 downto 0) := x"0";
  constant PSY_BAD_CONFIG : unsigned(3 downto 0) := x"1";
  constant PSY_BAD_SAMPLE : unsigned(3 downto 0) := x"2";
  constant PSY_BAD_SCALE : unsigned(3 downto 0) := x"3";

  function psy_minimum(a, b : integer) return integer;
  function psy_maximum(a, b : integer) return integer;
  function psy_min(a, b : psy_word_t) return psy_word_t;
  function psy_max(a, b : psy_word_t) return psy_word_t;
  function psy_scale(a : psy_word_t; amount : integer) return psy_word_t;
  function psy_clz(a : psy_word_t) return natural;
  function psy_norm(a : psy_word_t) return natural;
  function psy_abs(a : psy_word_t) return psy_word_t;
  function psy_mul_div2(a, b : psy_word_t) return psy_word_t;
  function psy_mul(a, b : psy_word_t) return psy_word_t;
  function psy_mul_div2_ds(a : psy_word_t; b : psy_half_t) return psy_word_t;
  function psy_mul_ds(a : psy_word_t; b : psy_half_t) return psy_word_t;
  function psy_slot(channel, window_index, band : natural;
                    short_block : std_logic) return natural;
  function psy_valid_offsets(offsets : psy_offsets_t; bands, length : natural)
    return boolean;
end package;

package body psy_pkg is
  function psy_minimum(a, b : integer) return integer is
  begin if a < b then return a; else return b; end if; end;
  function psy_maximum(a, b : integer) return integer is
  begin if a > b then return a; else return b; end if; end;
  function psy_min(a, b : psy_word_t) return psy_word_t is
  begin if a < b then return a; else return b; end if; end;
  function psy_max(a, b : psy_word_t) return psy_word_t is
  begin if a > b then return a; else return b; end if; end;
  function psy_scale(a : psy_word_t; amount : integer) return psy_word_t is
  begin
    if amount >= 0 then return shift_left(a, amount); end if;
    return shift_right(a, -amount);
  end;
  function psy_clz(a : psy_word_t) return natural is
    variable count : natural := 0;
  begin
    for i in 31 downto 0 loop
      exit when a(i) = '1';
      count := count + 1;
    end loop;
    return count;
  end;
  function psy_norm(a : psy_word_t) return natural is
  begin
    if a = PSY_ZERO then return 0; end if;
    if a(31) = '1' then return psy_clz(not a)-1; end if;
    return psy_clz(a)-1;
  end;
  function psy_abs(a : psy_word_t) return psy_word_t is
  begin if a < PSY_ZERO then return -a; else return a; end if; end;
  function psy_mul_div2(a, b : psy_word_t) return psy_word_t is
    variable product : signed(63 downto 0);
  begin product := a*b; return product(63 downto 32); end;
  function psy_mul(a, b : psy_word_t) return psy_word_t is
  begin return shift_left(psy_mul_div2(a,b),1); end;
  function psy_mul_div2_ds(a : psy_word_t; b : psy_half_t) return psy_word_t is
    variable product : signed(47 downto 0);
  begin product := a*b; return product(47 downto 16); end;
  function psy_mul_ds(a : psy_word_t; b : psy_half_t) return psy_word_t is
  begin return shift_left(psy_mul_div2_ds(a,b),1); end;
  function psy_slot(channel, window_index, band : natural;
                    short_block : std_logic) return natural is
  begin
    if short_block='1' then
      return channel*PSY_WINDOW_SLOTS + window_index*PSY_SHORT_BANDS + band;
    end if;
    return channel*PSY_WINDOW_SLOTS + band;
  end;
  function psy_valid_offsets(offsets : psy_offsets_t; bands, length : natural)
    return boolean is
  begin
    if bands=0 or bands>PSY_MAX_BANDS or offsets(0)/=0 then return false; end if;
    for i in 0 to PSY_MAX_BANDS-1 loop
      if i<bands then
        if offsets(i+1)<=offsets(i) or offsets(i+1)>length then return false; end if;
        -- The native energy routine reserves four headroom bits for <=128 lines.
        if offsets(i+1)-offsets(i)>128 then return false; end if;
      end if;
    end loop;
    return true;
  end;
end package body;
