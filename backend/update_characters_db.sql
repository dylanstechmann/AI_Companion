-- Add avatar columns to characters table (if not already present)
-- Run this in SQLite: sqlite3 data/companion.db < backend/update_characters_db.sql

-- Add columns
ALTER TABLE characters ADD COLUMN avatar_3d_url TEXT DEFAULT NULL;
ALTER TABLE characters ADD COLUMN body_type TEXT DEFAULT 'neutral';
ALTER TABLE characters ADD COLUMN clothing_style TEXT DEFAULT 'casual';
ALTER TABLE characters ADD COLUMN clothing_description TEXT DEFAULT '';
ALTER TABLE characters ADD COLUMN gender TEXT DEFAULT 'neutral';

-- Update default characters with avatar URLs
UPDATE characters SET 
  avatar_3d_url = '/avatars/greg_3d.glb',
  body_type = 'athletic',
  clothing_style = 'casual',
  clothing_description = 'Gray t-shirt, jeans, casual shoes',
  gender = 'male'
WHERE name = 'Greg';

UPDATE characters SET 
  avatar_3d_url = '/avatars/tiffany_3d.glb',
  body_type = 'curvy',
  clothing_style = 'business',
  clothing_description = 'White business shirt, business pants, formal shoes',
  gender = 'female'
WHERE name = 'Tiffany';

UPDATE characters SET 
  avatar_3d_url = '/avatars/friendly_ai_3d.glb',
  body_type = 'neutral',
  clothing_style = 'casual',
  clothing_description = 'Hoodie, casual pants, casual shoes',
  gender = 'female'
WHERE name = 'Friendly AI';

-- Verify updates
SELECT id, name, avatar_3d_url, body_type, gender FROM characters;