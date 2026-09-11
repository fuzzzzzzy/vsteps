-- ValoStep leaderboard schema (Cloudflare D1 / SQLite).
--
-- One row per player. name_key is the lowercase-normalized name used for
-- lookups/uniqueness (so "Ryan" and "ryan" are the same player); display_name
-- keeps whatever casing they actually typed, for showing on the board.
-- passphrase_hash is a SHA-256 hex digest, never the plaintext passphrase -
-- see functions/api/score.js for how it's checked.
--
-- correct/total track lifetime accuracy across every synced answer, and
-- best_streak is their best-ever streak - both accumulate across devices/
-- browsers as long as the same name+passphrase is used to sync.
--
-- Run this once against your D1 database (dashboard: D1 -> your database ->
-- Console -> paste this -> Execute). See README.md's leaderboard section
-- for the full setup walkthrough.

CREATE TABLE IF NOT EXISTS players (
  name_key TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  passphrase_hash TEXT NOT NULL,
  correct INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL DEFAULT 0,
  best_streak INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
