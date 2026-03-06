-- Add is_locked column to active_strategy table
ALTER TABLE active_strategy ADD COLUMN IF NOT EXISTS is_locked BOOLEAN DEFAULT FALSE;
