library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;
use std.textio.all;
use std.env.all;
use work.psy_pkg.all;

entity tb_psy_masking is
  generic(VECTOR_DIR : string := ".");
end entity;
architecture test of tb_psy_masking is
  signal clk : std_logic := '0';
  signal rst_n, cv, cr, lfe, calc, ov, ready, output_calc : std_logic := '0';
  signal bands : natural range 0 to 51 := 1;
  signal block_type : unsigned(1 downto 0) := "00";
  signal scale, history_scale, output_scale : integer range -3 to 31 := 0;
  signal pcm_shift : integer range -64 to 256 := 16;
  signal clip : psy_word_t := PSY_WORD_MAX;
  signal lo, hi, elo, ehi, pcm, energy, threshold, history : psy_band_words_t := (others=>PSY_ZERO);
  signal ot, old, oe, oh : psy_band_words_t;
  signal status : unsigned(3 downto 0);
begin
  clk<=not clk after 5 ns;
  dut : entity work.psy_masking
    port map(clk,rst_n,cv,cr,bands,block_type,scale,pcm_shift,lfe,clip,
      lo,hi,elo,ehi,pcm,to_signed(16#0148#,16),energy,threshold,history,history_scale,calc,
      ov,ready,status,ot,old,oe,oh,output_scale,output_calc);
  process
    file vectors : text open read_mode is VECTOR_DIR & "/masking.txt";
    variable row : line;
    variable cases, nb, block_v, exp, pcm_s, lf, hs, hc, out_hs, out_hc : integer;
    variable aa, bb, cc, dd, ee, ff, gg, hh : std_logic_vector(31 downto 0);
    variable expected_t, expected_ld, expected_e, expected_h : psy_band_words_t;
    variable compared : natural := 0;
    procedure tick is
    begin wait until rising_edge(clk); wait for 1 ns; end;
    procedure command is
    begin
      cv<='1'; loop wait until rising_edge(clk); exit when cr='1'; end loop;
      wait for 1 ns; cv<='0';
    end;
  begin
    tick; tick; rst_n<='1'; tick;
    bands<=0; command;
    while ov/='1' loop tick; end loop;
    assert status=PSY_BAD_CONFIG report "masking accepted zero bands" severity failure;
    ready<='1'; tick; ready<='0';
    bands<=1; scale<=31; history_scale<=0; calc<='1'; command;
    while ov/='1' loop tick; end loop;
    assert status=PSY_BAD_SCALE report "masking accepted undefined native shift domain" severity failure;
    ready<='1'; tick; ready<='0';
    -- Reset a running masking operation.
    scale<=0; calc<='0'; command; tick; rst_n<='0'; tick; rst_n<='1'; tick;
    assert cr='1' and ov='0' report "masking reset failed" severity failure;
    readline(vectors,row); read(row,cases);
    for job in 0 to cases-1 loop
      readline(vectors,row); read(row,nb); read(row,block_v); read(row,exp); read(row,pcm_s);
      read(row,lf); read(row,hs); read(row,hc); hread(row,aa);
      bands<=nb; block_type<=to_unsigned(block_v,2); scale<=exp; pcm_shift<=pcm_s;
      history_scale<=hs; clip<=signed(aa);
      if lf=1 then lfe<='1'; else lfe<='0'; end if;
      if hc=1 then calc<='1'; else calc<='0'; end if;
      for b in 0 to nb-1 loop
        readline(vectors,row);
        hread(row,aa); hread(row,bb); hread(row,cc); hread(row,dd);
        hread(row,ee); hread(row,ff); hread(row,gg); hread(row,hh);
        energy(b)<=signed(aa); threshold(b)<=signed(bb); history(b)<=signed(cc);
        pcm(b)<=signed(dd); lo(b)<=signed(ee); hi(b)<=signed(ff);
        elo(b)<=signed(gg); ehi(b)<=signed(hh);
      end loop;
      command;
      readline(vectors,row); read(row,out_hs); read(row,out_hc);
      for b in 0 to nb-1 loop
        readline(vectors,row); hread(row,aa); hread(row,bb); hread(row,cc); hread(row,dd);
        expected_t(b):=signed(aa); expected_ld(b):=signed(bb);
        expected_e(b):=signed(cc); expected_h(b):=signed(dd);
      end loop;
      while ov/='1' loop tick; end loop;
      assert status=PSY_OK and output_scale=out_hs and (output_calc='1')=(out_hc=1)
        report "masking history metadata mismatch job=" & integer'image(job) severity failure;
      for stall in 0 to job mod 5 loop
        for b in 0 to nb-1 loop
          assert ot(b)=expected_t(b) and old(b)=expected_ld(b)
            and oe(b)=expected_e(b) and oh(b)=expected_h(b)
            report "masking mismatch job=" & integer'image(job) & " band=" & integer'image(b)
              & " threshold=" & to_hstring(ot(b)) & "/" & to_hstring(expected_t(b))
              & " log=" & to_hstring(old(b)) & "/" & to_hstring(expected_ld(b))
              & " history=" & to_hstring(oh(b)) & "/" & to_hstring(expected_h(b)) severity failure;
        end loop;
        tick; assert ov='1' report "masking output lost under backpressure" severity failure;
      end loop;
      compared:=compared+nb; ready<='1'; tick; ready<='0';
    end loop;
    assert endfile(vectors) report "unconsumed masking vectors" severity failure;
    report "PASS: psy_masking " & integer'image(cases) & " windows; " & integer'image(compared) & " bands";
    finish;
  end process;
  process begin wait for 10 ms; assert false report "masking watchdog" severity failure; end process;
end architecture;
