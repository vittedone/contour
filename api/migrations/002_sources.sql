CREATE TABLE research (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    question text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE source (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    research_id uuid NOT NULL REFERENCES research ON DELETE CASCADE,
    kind text NOT NULL,
    name text NOT NULL,
    url text,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'ready', 'error')),
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    next_dispatch timestamptz NOT NULL DEFAULT now(),
    attempts integer NOT NULL DEFAULT 0,
    resolved_url text,
    html_snapshot bytea
);
CREATE INDEX source_by_research ON source (research_id, created_at);
CREATE INDEX pending_source ON source (next_dispatch)
    WHERE status IN ('queued', 'processing');

CREATE TABLE source_section (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id uuid NOT NULL REFERENCES source ON DELETE CASCADE,
    ordinal integer NOT NULL,
    page integer,
    heading text,
    body text NOT NULL,
    UNIQUE (source_id, ordinal)
);

CREATE TABLE fragment (
    section_id bigint NOT NULL REFERENCES source_section ON DELETE CASCADE,
    start_offset integer NOT NULL,
    end_offset integer NOT NULL,
    PRIMARY KEY (section_id, start_offset),
    CHECK (start_offset >= 0 AND end_offset > start_offset)
);
