"""Initial schema — full baseline for all 44 tables.

All ALTER TABLE ADD COLUMN statements from init_database() are baked in here
so a fresh MySQL install gets the complete schema in a single migration.

Revision ID: 0001
Revises:
Create Date: 2026-05-19
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# MySQL expression that produces ISO-8601 UTC text matching SQLite's datetime('now').
_NOW = "DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-%dT%H:%i:%sZ')"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS agents (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            token TEXT,
            token_hash TEXT,
            token_expires_at TEXT,
            password_hash TEXT,
            password_reset_token TEXT,
            password_reset_expires_at TEXT,
            wallet_address TEXT,
            points INTEGER DEFAULT 0,
            cash REAL DEFAULT 100000.0,
            deposited REAL DEFAULT 0.0,
            reputation_score INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ({_NOW}),
            updated_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS agent_messages (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            type TEXT NOT NULL,
            content TEXT,
            data TEXT,
            read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS agent_tasks (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            input_data TEXT,
            result_data TEXT,
            created_at TEXT DEFAULT ({_NOW}),
            updated_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS listings (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            seller_id INTEGER NOT NULL REFERENCES agents(id),
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT ({_NOW}),
            updated_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS orders (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            listing_id INTEGER NOT NULL REFERENCES listings(id),
            buyer_id INTEGER NOT NULL REFERENCES agents(id),
            seller_id INTEGER NOT NULL REFERENCES agents(id),
            price REAL NOT NULL,
            status TEXT DEFAULT 'pending_delivery',
            escrow_status TEXT DEFAULT 'held',
            created_at TEXT DEFAULT ({_NOW}),
            updated_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS arbitrators (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id INTEGER UNIQUE NOT NULL REFERENCES agents(id),
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS dispute_votes (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            arbitrator_id INTEGER NOT NULL REFERENCES arbitrators(id),
            vote TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            wallet_address TEXT,
            points INTEGER DEFAULT 0,
            verification_code TEXT,
            code_expires_at TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS points_transactions (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            amount INTEGER NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS user_tokens (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            token TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS rate_limits (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            client_ip TEXT NOT NULL,
            action TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            window_start TEXT NOT NULL,
            UNIQUE(client_ip, action)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS signals (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            signal_id INTEGER UNIQUE NOT NULL,
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            message_type TEXT NOT NULL,
            market TEXT NOT NULL,
            signal_type TEXT,
            symbol TEXT,
            token_id TEXT,
            outcome TEXT,
            accepted_reply_id INTEGER,
            symbols TEXT,
            side TEXT,
            entry_price REAL,
            exit_price REAL,
            quantity REAL,
            pnl REAL,
            title TEXT,
            content TEXT,
            tags TEXT,
            timestamp INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            executed_at TEXT
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS signal_replies (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            signal_id INTEGER NOT NULL REFERENCES signals(id),
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            content TEXT NOT NULL,
            accepted INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            leader_id INTEGER NOT NULL REFERENCES agents(id),
            follower_id INTEGER NOT NULL REFERENCES agents(id),
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS positions (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            leader_id INTEGER REFERENCES agents(id),
            symbol TEXT NOT NULL,
            market TEXT NOT NULL DEFAULT 'us-stock',
            token_id TEXT,
            outcome TEXT,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL,
            opened_at TEXT NOT NULL
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS signal_sequence (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS polymarket_settlements (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            position_id INTEGER NOT NULL REFERENCES positions(id),
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            symbol TEXT NOT NULL,
            token_id TEXT NOT NULL,
            outcome TEXT,
            quantity REAL NOT NULL,
            entry_price REAL NOT NULL,
            settlement_price REAL NOT NULL,
            proceeds REAL NOT NULL,
            market_slug TEXT,
            resolved_outcome TEXT,
            resolved_at TEXT,
            settled_at TEXT DEFAULT ({_NOW}),
            source_data TEXT
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS experiment_events (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            event_id TEXT UNIQUE NOT NULL,
            event_type TEXT NOT NULL,
            actor_agent_id INTEGER REFERENCES agents(id),
            target_agent_id INTEGER REFERENCES agents(id),
            object_type TEXT,
            object_id TEXT,
            market TEXT,
            experiment_key TEXT,
            variant_key TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS experiments (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            experiment_key TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'draft',
            unit_type TEXT DEFAULT 'agent',
            variants_json TEXT,
            start_at TEXT,
            end_at TEXT,
            created_at TEXT DEFAULT ({_NOW}),
            updated_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS experiment_assignments (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            experiment_key TEXT NOT NULL,
            unit_type TEXT NOT NULL,
            unit_id INTEGER NOT NULL,
            variant_key TEXT NOT NULL,
            assignment_reason TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT ({_NOW}),
            UNIQUE(experiment_key, unit_type, unit_id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS agent_reward_ledger (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            source_type TEXT,
            source_id TEXT,
            experiment_key TEXT,
            variant_key TEXT,
            status TEXT DEFAULT 'posted',
            metadata_json TEXT,
            created_at TEXT DEFAULT ({_NOW}),
            reversed_at TEXT
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS challenges (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            challenge_key TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            market TEXT NOT NULL,
            symbol TEXT,
            challenge_type TEXT NOT NULL,
            status TEXT DEFAULT 'upcoming',
            scoring_method TEXT DEFAULT 'return-only',
            initial_capital REAL DEFAULT 100000.0,
            max_position_pct REAL DEFAULT 100.0,
            max_drawdown_pct REAL DEFAULT 100.0,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            settled_at TEXT,
            rules_json TEXT,
            experiment_key TEXT,
            created_by_agent_id INTEGER REFERENCES agents(id),
            created_at TEXT DEFAULT ({_NOW}),
            updated_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS challenge_participants (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            challenge_id INTEGER NOT NULL REFERENCES challenges(id),
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            status TEXT DEFAULT 'joined',
            variant_key TEXT,
            joined_at TEXT DEFAULT ({_NOW}),
            starting_cash REAL DEFAULT 100000.0,
            ending_value REAL,
            return_pct REAL,
            max_drawdown REAL,
            trade_count INTEGER DEFAULT 0,
            rank INTEGER,
            disqualified_reason TEXT,
            UNIQUE(challenge_id, agent_id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS challenge_submissions (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            challenge_id INTEGER NOT NULL REFERENCES challenges(id),
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            signal_id INTEGER,
            submission_type TEXT NOT NULL,
            content TEXT,
            prediction_json TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS challenge_trades (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            challenge_id INTEGER NOT NULL REFERENCES challenges(id),
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            source_signal_id INTEGER NOT NULL,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            executed_at TEXT NOT NULL,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS challenge_results (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            challenge_id INTEGER NOT NULL REFERENCES challenges(id),
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            return_pct REAL,
            max_drawdown REAL,
            risk_adjusted_score REAL,
            quality_score REAL,
            final_score REAL,
            rank INTEGER,
            metrics_json TEXT,
            settled_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS signal_predictions (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            signal_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            market TEXT,
            symbol TEXT,
            direction TEXT,
            target_price REAL,
            target_probability REAL,
            confidence REAL,
            horizon_start_at TEXT,
            horizon_end_at TEXT,
            invalid_if TEXT,
            evidence_json TEXT,
            extracted_by TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS signal_quality_scores (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            signal_id INTEGER NOT NULL,
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            verifiability_score REAL DEFAULT 0,
            evidence_score REAL DEFAULT 0,
            specificity_score REAL DEFAULT 0,
            novelty_score REAL DEFAULT 0,
            review_score REAL DEFAULT 0,
            overall_score REAL DEFAULT 0,
            model_version TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS agent_metric_snapshots (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            window_key TEXT NOT NULL,
            window_start_at TEXT NOT NULL,
            window_end_at TEXT NOT NULL,
            return_pct REAL DEFAULT 0,
            max_drawdown REAL DEFAULT 0,
            trade_count INTEGER DEFAULT 0,
            strategy_count INTEGER DEFAULT 0,
            discussion_count INTEGER DEFAULT 0,
            reply_count INTEGER DEFAULT 0,
            accepted_reply_count INTEGER DEFAULT 0,
            citation_count INTEGER DEFAULT 0,
            adoption_count INTEGER DEFAULT 0,
            quality_score_avg REAL DEFAULT 0,
            risk_violation_count INTEGER DEFAULT 0,
            metadata_json TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS network_edges (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            source_agent_id INTEGER NOT NULL REFERENCES agents(id),
            target_agent_id INTEGER NOT NULL REFERENCES agents(id),
            edge_type TEXT NOT NULL,
            signal_id INTEGER,
            weight REAL DEFAULT 1,
            metadata_json TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS team_missions (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            mission_key TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            market TEXT NOT NULL,
            symbol TEXT,
            mission_type TEXT NOT NULL,
            status TEXT DEFAULT 'upcoming',
            team_size_min INTEGER DEFAULT 2,
            team_size_max INTEGER DEFAULT 5,
            assignment_mode TEXT DEFAULT 'random',
            required_roles_json TEXT,
            start_at TEXT NOT NULL,
            submission_due_at TEXT NOT NULL,
            settled_at TEXT,
            rules_json TEXT,
            experiment_key TEXT,
            created_at TEXT DEFAULT ({_NOW}),
            updated_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS teams (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            mission_id INTEGER NOT NULL REFERENCES team_missions(id),
            team_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'forming',
            formation_method TEXT DEFAULT 'manual',
            variant_key TEXT,
            created_at TEXT DEFAULT ({_NOW}),
            updated_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS team_mission_participants (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            mission_id INTEGER NOT NULL REFERENCES team_missions(id),
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            status TEXT DEFAULT 'joined',
            variant_key TEXT,
            joined_at TEXT DEFAULT ({_NOW}),
            UNIQUE(mission_id, agent_id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS team_members (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            team_id INTEGER NOT NULL REFERENCES teams(id),
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            role TEXT,
            status TEXT DEFAULT 'active',
            joined_at TEXT DEFAULT ({_NOW}),
            UNIQUE(team_id, agent_id)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS team_messages (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            team_id INTEGER NOT NULL REFERENCES teams(id),
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            signal_id INTEGER,
            message_type TEXT NOT NULL,
            content TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS team_submissions (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            mission_id INTEGER NOT NULL REFERENCES team_missions(id),
            team_id INTEGER NOT NULL REFERENCES teams(id),
            submitted_by_agent_id INTEGER NOT NULL REFERENCES agents(id),
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            prediction_json TEXT,
            confidence REAL,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS team_contributions (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            mission_id INTEGER NOT NULL REFERENCES team_missions(id),
            team_id INTEGER NOT NULL REFERENCES teams(id),
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            source_type TEXT NOT NULL,
            source_id TEXT,
            contribution_type TEXT NOT NULL,
            contribution_score REAL DEFAULT 0,
            metadata_json TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS team_results (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            mission_id INTEGER NOT NULL REFERENCES team_missions(id),
            team_id INTEGER NOT NULL REFERENCES teams(id),
            return_pct REAL,
            prediction_score REAL,
            quality_score REAL,
            consensus_gain REAL,
            final_score REAL,
            rank INTEGER,
            metrics_json TEXT,
            settled_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS market_news_snapshots (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            category TEXT NOT NULL,
            snapshot_key TEXT NOT NULL,
            items_json TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS macro_signal_snapshots (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            snapshot_key TEXT NOT NULL,
            verdict TEXT NOT NULL,
            bullish_count INTEGER NOT NULL DEFAULT 0,
            total_count INTEGER NOT NULL DEFAULT 0,
            signals_json TEXT NOT NULL,
            meta_json TEXT NOT NULL,
            source_json TEXT NOT NULL,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS etf_flow_snapshots (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            snapshot_key TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            etfs_json TEXT NOT NULL,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS stock_analysis_snapshots (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            symbol TEXT NOT NULL,
            market TEXT NOT NULL,
            analysis_id TEXT NOT NULL,
            current_price REAL NOT NULL,
            currency TEXT DEFAULT 'USD',
            signal TEXT NOT NULL,
            signal_score REAL NOT NULL,
            trend_status TEXT NOT NULL,
            support_levels_json TEXT NOT NULL,
            resistance_levels_json TEXT NOT NULL,
            bullish_factors_json TEXT NOT NULL,
            risk_factors_json TEXT NOT NULL,
            summary_text TEXT NOT NULL,
            analysis_json TEXT NOT NULL,
            news_json TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS profit_history (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id INTEGER NOT NULL REFERENCES agents(id),
            total_value REAL NOT NULL,
            cash REAL NOT NULL,
            position_value REAL NOT NULL,
            profit REAL NOT NULL,
            recorded_at TEXT DEFAULT ({_NOW})
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS agent_audit_log (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            agent_id INTEGER REFERENCES agents(id),
            action TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            created_at TEXT DEFAULT ({_NOW})
        )
    """)

    # ── Indexes ────────────────────────────────────────────────────────────────

    op.execute("CREATE INDEX IF NOT EXISTS idx_agents_token_hash ON agents(token_hash)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_profit_history_agent ON profit_history(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_profit_history_recorded_at ON profit_history(recorded_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_profit_history_agent_recorded_at ON profit_history(agent_id, recorded_at DESC)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_agent ON positions(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_market_symbol ON positions(market, symbol)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_positions_polymarket_token ON positions(market, token_id)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_signals_agent ON signals(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_signals_agent_message_type ON signals(agent_id, message_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_signals_message_type ON signals(message_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_signals_polymarket_token ON signals(market, token_id)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_polymarket_settlements_agent ON polymarket_settlements(agent_id, settled_at DESC)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_experiment_events_type_created ON experiment_events(event_type, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_experiment_events_actor_created ON experiment_events(actor_agent_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_experiment_events_target_created ON experiment_events(target_agent_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_experiment_events_experiment_variant_created ON experiment_events(experiment_key, variant_key, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_experiment_events_object ON experiment_events(object_type, object_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_experiment_assignments_experiment_variant ON experiment_assignments(experiment_key, variant_key)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_reward_ledger_agent_created ON agent_reward_ledger(agent_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_reward_ledger_source ON agent_reward_ledger(source_type, source_id)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_challenges_status_end ON challenges(status, end_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_challenges_key ON challenges(challenge_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_challenge_participants_agent ON challenge_participants(agent_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_challenge_participants_challenge_rank ON challenge_participants(challenge_id, rank)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_challenge_submissions_challenge_created ON challenge_submissions(challenge_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_challenge_trades_challenge_agent ON challenge_trades(challenge_id, agent_id, executed_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_challenge_trades_source_signal ON challenge_trades(source_signal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_challenge_results_challenge_rank ON challenge_results(challenge_id, rank)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_signal_predictions_signal ON signal_predictions(signal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_signal_predictions_agent_created ON signal_predictions(agent_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_signal ON signal_quality_scores(signal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_signal_quality_scores_agent_created ON signal_quality_scores(agent_id, created_at)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_metric_snapshots_agent_window ON agent_metric_snapshots(agent_id, window_key, window_end_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_metric_snapshots_window ON agent_metric_snapshots(window_key, window_end_at)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_network_edges_source_created ON network_edges(source_agent_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_network_edges_target_created ON network_edges(target_agent_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_network_edges_type_created ON network_edges(edge_type, created_at)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_team_missions_status_due ON team_missions(status, submission_due_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_missions_key ON team_missions(mission_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_teams_mission_status ON teams(mission_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_teams_key ON teams(team_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_mission_participants_agent ON team_mission_participants(agent_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_mission_participants_mission ON team_mission_participants(mission_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_members_agent ON team_members(agent_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_messages_team_created ON team_messages(team_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_messages_signal ON team_messages(signal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_submissions_team_created ON team_submissions(team_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_submissions_mission ON team_submissions(mission_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_contributions_mission_agent ON team_contributions(mission_id, agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_contributions_team ON team_contributions(team_id, contribution_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_results_mission_rank ON team_results(mission_id, rank)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_market_news_category_created ON market_news_snapshots(category, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_market_news_snapshot_key ON market_news_snapshots(snapshot_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_macro_signal_created ON macro_signal_snapshots(created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_macro_signal_snapshot_key ON macro_signal_snapshots(snapshot_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_etf_flow_created ON etf_flow_snapshots(created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_etf_flow_snapshot_key ON etf_flow_snapshots(snapshot_key)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stock_analysis_symbol_created ON stock_analysis_snapshots(symbol, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stock_analysis_market_symbol ON stock_analysis_snapshots(market, symbol)")

    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_agent_created ON agent_audit_log(agent_id, created_at)")


def downgrade() -> None:
    # Drop in reverse dependency order.
    tables = [
        "agent_audit_log",
        "profit_history",
        "stock_analysis_snapshots",
        "etf_flow_snapshots",
        "macro_signal_snapshots",
        "market_news_snapshots",
        "team_results",
        "team_contributions",
        "team_submissions",
        "team_messages",
        "team_members",
        "team_mission_participants",
        "teams",
        "team_missions",
        "network_edges",
        "agent_metric_snapshots",
        "signal_quality_scores",
        "signal_predictions",
        "challenge_results",
        "challenge_trades",
        "challenge_submissions",
        "challenge_participants",
        "challenges",
        "agent_reward_ledger",
        "experiment_assignments",
        "experiments",
        "experiment_events",
        "polymarket_settlements",
        "signal_sequence",
        "positions",
        "subscriptions",
        "signal_replies",
        "signals",
        "rate_limits",
        "user_tokens",
        "points_transactions",
        "users",
        "dispute_votes",
        "arbitrators",
        "orders",
        "listings",
        "agent_tasks",
        "agent_messages",
        "agents",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
