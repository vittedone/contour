ALTER TABLE research ADD COLUMN is_demo boolean NOT NULL DEFAULT false;
CREATE UNIQUE INDEX research_single_demo ON research (is_demo) WHERE is_demo;
