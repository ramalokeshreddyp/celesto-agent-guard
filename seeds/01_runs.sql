-- Create runs table for the Celesto Agent Guard run ledger
CREATE TABLE IF NOT EXISTS runs (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(255) UNIQUE NOT NULL,
    sandbox_name VARCHAR(255) NOT NULL,
    problem_id VARCHAR(255) NOT NULL,
    state VARCHAR(50) NOT NULL CHECK (state IN ('created', 'ready', 'running', 'succeeded', 'failed', 'deleted')),
    execution_target VARCHAR(50) NOT NULL CHECK (execution_target = 'celesto_sandbox'),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Seed a demo row that the reviewer requires
INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
VALUES (
    'seed-run-001',
    'sbx-seeddemo1',
    'autograder-baseline',
    'deleted',
    'celesto_sandbox'
)
ON CONFLICT (run_id) DO NOTHING;
