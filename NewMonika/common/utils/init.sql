CREATE TABLE IF NOT EXISTS advices (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    username TEXT NOT NULL,
    chat_id BIGINT NOT NULL,
    content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wallets (
    user_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL,
    balance BIGINT DEFAULT 0,
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS warnings (
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    username TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    last_reason TEXT,
    last_warned_at TIMESTAMP DEFAULT now(),
    PRIMARY KEY (user_id, chat_id)
);
