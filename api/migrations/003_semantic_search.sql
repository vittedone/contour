ALTER TABLE fragment ADD COLUMN embedding vector(384);

CREATE INDEX fragment_pending_embedding ON fragment (section_id, start_offset) WHERE embedding IS NULL;

CREATE TABLE analysis (
    research_id uuid PRIMARY KEY REFERENCES research ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('queued','processing','ready','error')),
    attempts integer NOT NULL DEFAULT 0,
    next_dispatch timestamptz NOT NULL DEFAULT now(),
    error text
);

CREATE TABLE search_hit (
    research_id uuid NOT NULL REFERENCES analysis ON DELETE CASCADE,
    rank integer NOT NULL,
    section_id bigint NOT NULL,
    fragment_start integer NOT NULL,
    similarity real NOT NULL,
    claim_start integer,
    claim_end integer,
    PRIMARY KEY (research_id, rank),
    FOREIGN KEY (section_id, fragment_start) REFERENCES fragment ON DELETE CASCADE,
    CHECK ((claim_start IS NULL) = (claim_end IS NULL)),
    CHECK (claim_start >= fragment_start AND claim_end > claim_start)
);
