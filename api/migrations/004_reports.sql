CREATE TABLE report (
    research_id uuid NOT NULL REFERENCES research ON DELETE CASCADE,
    version integer NOT NULL CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    content jsonb NOT NULL,
    PRIMARY KEY (research_id, version)
);
