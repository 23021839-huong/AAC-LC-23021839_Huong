library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;
use std.env.all;
use work.psy_pkg.all;

entity tb_psy_math is
  generic(VECTOR_DIR : string := ".");
end entity;
architecture test of tb_psy_math is
  signal clk : std_logic := '0';
  signal rst_n, iv, ir, ov, ready : std_logic := '0';
  signal input_data, output_data : psy_word_t := PSY_ZERO;
begin
  clk<=not clk after 5 ns;
  dut : entity work.psy_log2 port map(clk,rst_n,iv,ir,input_data,ov,ready,output_data);
  process
    file vectors : text open read_mode is VECTOR_DIR & "/primitives.txt";
    variable row : line;
    variable operation, count : integer := 0;
    variable aa, bb, ee : std_logic_vector(31 downto 0);
    variable actual, expected : psy_word_t;
    procedure tick is
    begin wait until rising_edge(clk); wait for 1 ns; end;
  begin
    tick; tick; rst_n<='1'; tick;
    -- Reset during polynomial evaluation must cancel the request.
    input_data<=to_signed(1234567,32); iv<='1'; tick; iv<='0';
    tick; rst_n<='0'; tick; rst_n<='1'; tick;
    assert ov='0' and ir='1' report "log reset did not cancel request" severity failure;
    while not endfile(vectors) loop
      readline(vectors,row); read(row,operation); hread(row,aa); hread(row,bb); hread(row,ee);
      expected:=signed(ee);
      case operation is
        when 0 => actual:=psy_mul(signed(aa),signed(bb));
        when 1 => actual:=psy_mul_div2(signed(aa),signed(bb));
        when 2 => actual:=psy_mul_ds(signed(aa),signed(bb(15 downto 0)));
        when 3 => actual:=psy_mul_div2_ds(signed(aa),signed(bb(15 downto 0)));
        when 4 => actual:=to_signed(psy_norm(signed(aa)),32);
        when 5 => actual:=to_signed(psy_clz(signed(aa)),32);
        when 6 =>
          input_data<=signed(aa); iv<='1';
          loop wait until rising_edge(clk); exit when ir='1'; end loop;
          wait for 1 ns; iv<='0';
          while ov/='1' loop tick; end loop;
          for stall in 0 to count mod 4 loop
            assert output_data=expected report "log2 mismatch at vector " & integer'image(count)
              & " input=" & to_hstring(aa) & " expected=" & to_hstring(ee)
              & " actual=" & to_hstring(output_data) severity failure;
            tick;
            assert ov='1' report "log result lost under backpressure" severity failure;
          end loop;
          actual:=output_data; ready<='1'; tick; ready<='0';
        when others => assert false report "invalid arithmetic opcode" severity failure;
      end case;
      assert actual=expected report "math mismatch at vector " & integer'image(count)
        & " op=" & integer'image(operation) & " expected=" & to_hstring(expected)
        & " actual=" & to_hstring(actual) severity failure;
      count:=count+1;
    end loop;
    report "PASS: psy_math " & integer'image(count) & " native helper comparisons";
    finish;
  end process;
  process begin wait for 10 ms; assert false report "psy_math watchdog" severity failure; end process;
end architecture;
