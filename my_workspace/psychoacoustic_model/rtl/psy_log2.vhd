-------------------------------------------------------------------------------
-- CalcLdData(x) = fLog2(x,0), translated from libFDK/include/fixpoint_math.h.
-- LDCOEFF_16BIT profile. Ten polynomial iterations; no real-valued arithmetic.
-- Output is held stable until accepted. Reset cancels an outstanding request.
-- New implementation, 2026-10-17; see repository NOTICE for FDK-derived work.
-------------------------------------------------------------------------------
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use work.psy_pkg.all;

entity psy_log2 is
  port (
    clk, rst_n : in std_logic;
    in_valid : in std_logic;
    in_ready : out std_logic;
    in_data : in psy_word_t;
    out_valid : out std_logic;
    out_ready : in std_logic;
    out_data : out psy_word_t
  );
end entity;

architecture rtl of psy_log2 is
  type state_t is (IDLE, POLYNOMIAL, CONVERT_BASE, ADD_EXPONENT, OUTPUT_RESULT);
  signal state : state_t := IDLE;
  type coefficients_t is array(0 to 9) of integer range -32768 to 0;
  constant COEFFICIENTS : coefficients_t :=
    (-32768,-16384,-10923,-8192,-6554,-5461,-4681,-4096,-3641,-3277);
  constant TWO_LOG2_E_MINUS_ONE : psy_word_t := x"71547653";
  signal x, power, accumulator, result : psy_word_t := PSY_ZERO;
  signal iteration : natural range 0 to 9 := 0;
  signal input_exponent : integer range -30 to 0 := 0;
begin
  in_ready <= '1' when state=IDLE and rst_n='1' else '0';
  out_valid <= '1' when state=OUTPUT_RESULT and rst_n='1' else '0';
  out_data <= result;
  process(clk)
    variable normalization, enorm : natural;
    variable mapped, combined : psy_word_t;
  begin
    if rising_edge(clk) then
      if rst_n='0' then
        state<=IDLE; result<=PSY_ZERO;
      else
        case state is
          when IDLE =>
            if in_valid='1' then
              if in_data<=PSY_ZERO then
                result<=PSY_WORD_MIN; state<=OUTPUT_RESULT;
              else
                normalization:=psy_clz(in_data)-1;
                mapped:=-(shift_left(in_data,normalization)+PSY_WORD_MIN);
                x<=mapped; power<=mapped; accumulator<=PSY_ZERO;
                input_exponent<=-integer(normalization);
                iteration<=0; state<=POLYNOMIAL;
              end if;
            end if;
          when POLYNOMIAL =>
            accumulator<=accumulator+psy_mul_div2_ds(power,to_signed(COEFFICIENTS(iteration),16));
            power<=psy_mul(power,x);
            if iteration=9 then state<=CONVERT_BASE; else iteration<=iteration+1; end if;
          when CONVERT_BASE =>
            accumulator<=accumulator+psy_mul_div2(accumulator,TWO_LOG2_E_MINUS_ONE);
            state<=ADD_EXPONENT;
          when ADD_EXPONENT =>
            if input_exponent/=0 then
              enorm:=32-psy_norm(to_signed(input_exponent,32));
              combined:=shift_right(accumulator,enorm-1)
                +shift_left(to_signed(input_exponent,32),31-enorm);
              result<=psy_scale(combined,integer(enorm)-6);
            else
              result<=shift_right(accumulator,5);
            end if;
            state<=OUTPUT_RESULT;
          when OUTPUT_RESULT =>
            if out_ready='1' then state<=IDLE; end if;
        end case;
      end if;
    end if;
  end process;
end architecture;
