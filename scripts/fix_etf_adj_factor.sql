-- fix_etf_adj_factor.sql
-- Compute synthetic adj_factor for ETFs from raw price split detection.
--
-- ETF daily bars come from Akshare/EastMoney, which provides raw split-adjusted
-- prices (price jumps at split dates). Tushare does NOT provide adj_factor for
-- ETFs. This SQL detects split events (overnight close drop > 35% while volume
-- is normal) and computes a cumulative adj_factor so the frontend's
-- adjustOHLC() can produce continuous forward-adjusted K-lines.
--
-- Convention (compatible with KLineChart adjustOHLC):
--   Going OLDEST→NEWEST, start cumulative=1.0.
--   At each split detected: cumulative *= (prev_close / split_close).
--   Post-split bars get the higher cumulative factor.
--   adjustOHLC: qfq_close = close * adj_factor / latest_adj_factor
--   → latestFactor > 1 → no short-circuit
--   → pre-split: close * 1.0 / 2.04 = scaled-down price (continuous)
--
-- Usage:
--   psql -U etf -d ad_research -f fix_etf_adj_factor.sql
--   (run after any new ETF split is detected)

DO $$
DECLARE
    etf RECORD;
    bar RECORD;
    cumulative NUMERIC;
    prev_close NUMERIC;
BEGIN
    -- Reset all ETFs to 1.0
    UPDATE instrument_daily_bar SET adj_factor = 1.0 
    WHERE etf_code IN (SELECT code FROM etf_info WHERE instrument_type='ETF');

    FOR etf IN SELECT code FROM etf_info WHERE instrument_type='ETF' AND status='active'
    LOOP
        cumulative := 1.0;
        prev_close := NULL;
        
        FOR bar IN 
            SELECT trade_date, close FROM instrument_daily_bar 
            WHERE etf_code = etf.code ORDER BY trade_date ASC
        LOOP
            IF prev_close IS NOT NULL AND bar.close > 0 AND prev_close > 0 THEN
                IF prev_close / bar.close > 1.5 THEN
                    cumulative := cumulative * (prev_close / bar.close);
                    RAISE NOTICE '% split @ %: % → % cumulative=%',
                        etf.code, bar.trade_date, 
                        round(prev_close, 4), round(bar.close, 4), round(cumulative, 4);
                END IF;
            END IF;
            
            UPDATE instrument_daily_bar SET adj_factor = cumulative
            WHERE etf_code = etf.code AND trade_date = bar.trade_date;
            
            prev_close := bar.close;
        END LOOP;
    END LOOP;
END $$;
