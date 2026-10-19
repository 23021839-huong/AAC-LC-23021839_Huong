library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;
use std.env.all;
use work.psy_pkg.all;

entity tb_psy_sfb_frontend is
  generic(VECTOR_DIR : string := ".");
end entity;
architecture test of tb_psy_sfb_frontend is
  signal clk : std_logic := '0';
  signal rst_n, cv, cr, short_block, iv, ir, sv, sr, bv, br, rv, rr, rz, busy : std_logic := '0';
  signal channels : natural range 1 to 2 := 1;
  signal exponent : integer range 0 to 31 := 12;
  signal bands : natural range 0 to 51 := 1;
  signal lowpass : natural range 0 to 1024 := 4;
  signal offsets : psy_offsets_t := (0=>0,others=>4);
  signal input_data, spec_data, energy, ld, threshold : psy_word_t := PSY_ZERO;
  signal sc, bc : natural range 0 to 1;
  signal si : natural range 0 to 1023;
  signal bw : natural range 0 to 7;
  signal bi : natural range 0 to 50;
  signal hr : natural range 0 to 30;
  signal status : unsigned(3 downto 0);
  signal result_scale : integer range -3 to 31;
  signal result_shift : natural range 0 to 30;
begin
  clk<=not clk after 5 ns;
  dut : entity work.psy_sfb_frontend
    port map(clk,rst_n,cv,cr,short_block,channels,exponent,bands,lowpass,offsets,
      iv,ir,input_data,sv,sr,sc,si,spec_data,bv,br,bc,bw,bi,hr,energy,ld,threshold,
      rv,rr,status,result_scale,result_shift,rz,busy);
  process
    file vectors : text open read_mode is VECTOR_DIR & "/frontend.txt";
    variable row : line;
    variable cases, nc, ns, exp, nb, lp, v, expected_scale, expected_shift, expected_zero : integer;
    variable expected_hr, total_words, total_bands : integer := 0;
    variable bits, ee, ll, tt : std_logic_vector(31 downto 0);
    variable table_offsets : psy_offsets_t;
    variable held : psy_word_t;
    procedure tick is
    begin wait until rising_edge(clk); wait for 1 ns; end;
    procedure command is
    begin
      cv<='1';
      loop wait until rising_edge(clk); exit when cr='1'; end loop;
      wait for 1 ns; cv<='0';
    end;
    procedure consume_error(code : unsigned(3 downto 0)) is
    begin
      while rv/='1' loop tick; end loop;
      assert status=code and sv='0' and bv='0' report "incorrect frontend error response" severity failure;
      tick; assert rv='1' and status=code report "error response not held" severity failure;
      rr<='1'; tick; rr<='0';
    end;
  begin
    tick; tick; rst_n<='1'; tick;
    -- Invalid descriptors must not request spectrum or emit checkpoint payload.
    bands<=0; command; consume_error(PSY_BAD_CONFIG);
    bands<=1; lowpass<=5; command; consume_error(PSY_BAD_CONFIG);
    lowpass<=4;
    -- Cancel a partly loaded job, then begin a clean job without stale state.
    command;
    iv<='1'; input_data<=to_signed(123,32);
    for i in 1 to 17 loop tick; end loop;
    rst_n<='0'; tick; iv<='0'; rst_n<='1'; tick;
    assert cr='1' and sv='0' and bv='0' and rv='0' report "frontend reset failed" severity failure;
    -- INT_MIN inside the retained band is rejected after draining the input.
    command; iv<='1';
    for i in 0 to 1023 loop
      input_data<=PSY_ZERO; if i=0 then input_data<=PSY_WORD_MIN; end if;
      loop wait until rising_edge(clk); exit when ir='1'; end loop;
      wait for 1 ns;
    end loop;
    iv<='0'; consume_error(PSY_BAD_SAMPLE);
    readline(vectors,row); read(row,cases);
    for job in 0 to cases-1 loop
      readline(vectors,row); read(row,nc); read(row,ns); read(row,exp); read(row,nb); read(row,lp);
      channels<=nc; exponent<=exp; bands<=nb; lowpass<=lp;
      if ns=1 then short_block<='1'; else short_block<='0'; end if;
      table_offsets:=(others=>0);
      readline(vectors,row);
      for b in 0 to nb loop read(row,v); table_offsets(b):=v; end loop;
      offsets<=table_offsets; command;
      for i in 0 to nc*1024-1 loop
        readline(vectors,row); hread(row,bits); input_data<=signed(bits); iv<='1';
        if i mod 17=0 then iv<='0'; tick; iv<='1'; end if;
        loop wait until rising_edge(clk); exit when ir='1'; end loop;
        wait for 1 ns;
      end loop;
      iv<='0';
      readline(vectors,row); read(row,expected_scale); read(row,expected_shift); read(row,expected_zero);
      for i in 0 to nc*1024-1 loop
        readline(vectors,row); hread(row,bits);
        while sv/='1' loop tick; end loop;
        held:=spec_data;
        if i mod 31=0 then
          tick; tick;
          assert sv='1' and spec_data=held report "spectrum changed under backpressure" severity failure;
        end if;
        assert sc=i/1024 and si=i mod 1024 and spec_data=signed(bits)
          report "frontend spectrum mismatch job=" & integer'image(job) & " index=" & integer'image(i)
          & " expected=" & to_hstring(bits) & " actual=" & to_hstring(spec_data) severity failure;
        sr<='1'; tick; sr<='0'; total_words:=total_words+1;
      end loop;
      for c in 0 to nc-1 loop
        for w in 0 to ns*7 loop
          for b in 0 to nb-1 loop
            readline(vectors,row); read(row,expected_hr); hread(row,ee); hread(row,ll); hread(row,tt);
            while bv/='1' loop tick; end loop;
            assert bc=c and bw=w and bi=b report "frontend band address mismatch" severity failure;
            assert hr=expected_hr and energy=signed(ee) and ld=signed(ll) and threshold=signed(tt)
              report "frontend band mismatch job=" & integer'image(job) & " band=" & integer'image(b)
              & " energy=" & to_hstring(energy) & "/" & to_hstring(ee)
              & " ld=" & to_hstring(ld) & "/" & to_hstring(ll)
              & " threshold=" & to_hstring(threshold) & "/" & to_hstring(tt) severity failure;
            if b mod 7=0 then
              tick; tick;
              assert bv='1' and energy=signed(ee) and ld=signed(ll) and bi=b
                report "band result changed under backpressure" severity failure;
            end if;
            br<='1'; tick; br<='0'; total_bands:=total_bands+1;
          end loop;
        end loop;
      end loop;
      while rv/='1' loop tick; end loop;
      assert status=PSY_OK and result_scale=expected_scale and result_shift=expected_shift
        report "frontend summary mismatch job=" & integer'image(job) severity failure;
      assert (rz='1')=(expected_zero=1) report "zero-spectrum flag mismatch" severity failure;
      tick; tick; assert rv='1' report "summary lost under backpressure" severity failure;
      rr<='1'; tick; rr<='0';
    end loop;
    assert endfile(vectors) report "unconsumed frontend vectors" severity failure;
    report "PASS: psy_sfb_frontend " & integer'image(cases) & " jobs; "
      & integer'image(total_words) & " spectrum words; " & integer'image(total_bands) & " bands";
    finish;
  end process;
  process begin wait for 30 ms; assert false report "frontend watchdog" severity failure; end process;
end architecture;
