-- NewsAlgo Supabase テーブル定義
-- Supabase SQL Editorで実行してください

CREATE TABLE IF NOT EXISTS news_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    item_id TEXT,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    credibility FLOAT,
    is_reliable BOOLEAN,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    raw TEXT,
    url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS signal_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    item_id TEXT,
    source TEXT,
    score FLOAT NOT NULL,
    level TEXT NOT NULL,  -- STRONG / MEDIUM / NONE
    direction TEXT NOT NULL,  -- bullish / bearish / neutral
    affected_symbols TEXT[],
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    order_id TEXT UNIQUE NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,  -- buy / sell
    quantity FLOAT NOT NULL,
    fill_price FLOAT,
    status TEXT NOT NULL,
    signal_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- インデックス
CREATE INDEX IF NOT EXISTS idx_news_log_timestamp ON news_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_log_level ON signal_log(level, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_order_log_symbol ON order_log(symbol, created_at DESC);

-- Row Level Security（必要に応じて有効化）
-- ALTER TABLE news_log ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE signal_log ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE order_log ENABLE ROW LEVEL SECURITY;
