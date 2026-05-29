async def m001_initial(db):
    """Initial Agent Wallet tables."""

    await db.execute(
        f"""
        CREATE TABLE agent_wallet.profiles (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            wallet TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            template TEXT NOT NULL DEFAULT 'agent_wallet',
            acl_id TEXT NOT NULL,
            token_id TEXT NOT NULL,
            token_name TEXT,
            token_hint TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            lightning_address TEXT,
            lnurlp_id TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )

    await db.execute(
        f"""
        CREATE TABLE agent_wallet.policies (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            single_payment_limit_sats INTEGER NOT NULL DEFAULT 100,
            daily_limit_sats INTEGER NOT NULL DEFAULT 1000,
            allow_spending BOOLEAN NOT NULL DEFAULT FALSE,
            allow_lnurl_pay BOOLEAN NOT NULL DEFAULT FALSE,
            allow_lightning_address_pay BOOLEAN NOT NULL DEFAULT FALSE,
            allow_lnurl_withdraw BOOLEAN NOT NULL DEFAULT FALSE,
            dry_run_required BOOLEAN NOT NULL DEFAULT TRUE,
            approval_required_above_sats INTEGER,
            allowed_domains TEXT,
            allowed_lnurl_domains TEXT,
            allowed_lightning_addresses TEXT,
            denied_domains TEXT,
            denied_lightning_addresses TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )

    await db.execute(
        f"""
        CREATE TABLE agent_wallet.activity_events (
            id TEXT PRIMARY KEY,
            wallet TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            token_id TEXT,
            event_type TEXT NOT NULL,
            amount_sats INTEGER,
            destination TEXT,
            payment_hash TEXT,
            checking_id TEXT,
            status TEXT NOT NULL,
            reason TEXT,
            task_id TEXT,
            request_json TEXT,
            response_json TEXT,
            metadata TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
        """
    )


async def m002_daily_spend_bucket(db):
    await db.execute(
        f"""
        CREATE TABLE agent_wallet.daily_spend (
            profile_id TEXT NOT NULL,
            day INTEGER NOT NULL,
            spent_sats INTEGER NOT NULL DEFAULT 0,
            pending_sats INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            PRIMARY KEY (profile_id, day)
        );
        """
    )
