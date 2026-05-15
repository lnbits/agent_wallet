# the migration file is where you build your database tables
# If you create a new release for your extension ,
# remember the migration file is like a blockchain, never edit only add!

empty_dict: dict[str, str] = {}




async def m002_profiles(db):
    """
    Initial profiles table.
    """

    await db.execute(
        f"""
        CREATE TABLE agent_wallet.profiles (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            wallet TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            acl_id TEXT NOT NULL,
            token_id TEXT NOT NULL,
            token_name TEXT,
            status TEXT NOT NULL,
            lnurlp_id TEXT,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
    """
    )


async def m003_client_data(db):
    """
    Initial client data table.
    """

    await db.execute(
        f"""
        CREATE TABLE agent_wallet.client_data (
            id TEXT PRIMARY KEY,
            profiles_id TEXT NOT NULL,
            name TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            updated_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now}
        );
    """
    )