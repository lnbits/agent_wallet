<a href="https://lnbits.com" target="_blank" rel="noopener noreferrer">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://i.imgur.com/QE6SIrs.png">
    <img src="https://i.imgur.com/fyKPgVT.png" alt="LNbits" style="width:280px">
  </picture>
</a>

[![License: MIT](https://img.shields.io/badge/License-MIT-success?logo=open-source-initiative&logoColor=white)](./LICENSE)
[![Built for LNbits](https://img.shields.io/badge/Built%20for-LNbits-4D4DFF?logo=lightning&logoColor=white)](https://github.com/lnbits/lnbits)

# Agent Wallet - <small>[LNbits](https://github.com/lnbits/lnbits) extension</small>

## Getting started

1. Create a scoped ACL token in LNbits.
2. Create an agent profile in the extension (bind the token, set policy).
3. Copy the MCP config or "Copy for my AI agent" prompt.
4. Paste into your MCP client or agent chat.

## Controlled Lightning wallets for AI agents

Agent Wallet binds an LNbits wallet and a pre-created ACL token to an agent profile. The agent can then use a restricted runtime API for receiving invoices, checking wallet state, making controlled payments, and recording an activity trail.

The extension stores token references only. It does not store raw API token secrets.

## Features

- **Agent profiles** - bind a wallet, ACL token, policy, and optional Lightning Address to each agent.
- **Restricted runtime API** - runtime endpoints require the exact API token bound to the profile.
- **Receive invoices** - agents can create invoices into the bound wallet.
- **Controlled spending** - set single-payment limits, daily limits, dry-run requirements, and optional approval thresholds.
- **LNURL support** - allow LNURL-pay, Lightning Address payments, and LNURL-withdraw claims per profile.
- **Activity log** - track invoices, dry-runs, denied attempts, payments, and failures.
- **MCP connector config** - copy a ready-to-edit MCP server JSON block for agent tooling.

## Overview

Agent Wallet is for giving automated agents Lightning capabilities without handing them broad wallet access. You create the ACL token in LNbits first, scope it to the routes the agent needs, then bind that token to an Agent Wallet profile.

Each profile has its own policy. Spending is disabled by default, dry-run checks are enabled by default, and LNURL permissions are opt-in.

Use Agent Wallet for:

- AI agents that need to receive sats for work or API calls
- Agents that can pay small invoices inside a fixed budget
- Tooling that needs a revocable Lightning credential
- MCP or script-based workflows that should not use a full wallet admin key

## Requirements

- LNbits `1.4.2` or newer
- A wallet owned by the signed-in account
- A scoped LNbits ACL token created before profile setup
- Optional: LNURLp enabled for Lightning Address / LNURL-pay helper flows

## Usage

1. **Create a scoped ACL token** in LNbits.

   Keep the raw bearer token somewhere safe. Agent Wallet will only list and store the token reference.

   Add the ACL route `/agent_wallet/api/v1`. Grant `GET` for status, balance, and payment-status reads. Grant `POST` for invoice, dry-run, and payment calls. Fine-grained agent permissions are controlled by the Agent Wallet policy below.

2. **Enable** the Agent Wallet extension.

3. **Create** a new agent profile.

   Fill in:

   - Wallet
   - Agent name
   - ACL token
   - Optional LNURLp pay link or Lightning Address
   - Policy limits and permissions

4. **Configure the policy**.

   Important defaults:

   - Spending is off
   - LNURL-pay is off
   - Lightning Address pay is off
   - LNURL-withdraw is off
   - Dry-run before payment is on

5. **Expand** the profile row to view activity and copy MCP config.

   Paste the raw restricted bearer token into your agent runtime or MCP environment. Do not paste a full wallet admin key.

## Policy Controls

Agent Wallet policies are deliberately simple:

- **Single payment limit sats** - maximum amount for one outgoing payment.
- **Daily limit sats** - maximum reserved/spent amount per UTC day.
- **Allow spending** - required for BOLT11, LNURL-pay, and Lightning Address payments.
- **Dry-run required** - requires a matching dry-run before payment execution.
- **Approval above sats** - marks larger payments as requiring approval instead of executing.
- **Allow LNURL-pay** - permits LNURL-pay destinations.
- **Allow Lightning Address pay** - permits payments to addresses such as `alice@example.com`.
- **Allow LNURL-withdraw** - permits the agent to claim LNURL-withdraw links into the bound wallet.

LNURL-withdraw is treated as receiving funds into the wallet, not as spending from the wallet.

## Runtime API

Runtime routes are bound to a profile and require the profile's ACL token.

Useful endpoints:

```text
GET  /agent_wallet/api/v1/profiles/{profile_id}/runtime/status
GET  /agent_wallet/api/v1/profiles/{profile_id}/runtime/balance
POST /agent_wallet/api/v1/profiles/{profile_id}/runtime/invoice
POST /agent_wallet/api/v1/profiles/{profile_id}/runtime/dry-run
POST /agent_wallet/api/v1/profiles/{profile_id}/runtime/pay
GET  /agent_wallet/api/v1/profiles/{profile_id}/runtime/payments/{checking_id}
```

The normal profile-management and activity routes are browser/account routes and reject API-token access.

LNbits ACLs gate the broad `/agent_wallet/api/v1` route by HTTP method. Agent Wallet policies decide what the bound agent can actually do: receive only, spend, use LNURL-pay, use Lightning Address, claim LNURL-withdraw, require dry-runs, and enforce limits.

## MCP Connector

Each profile can show a JSON snippet for an MCP server configuration:

```json
{
  "mcpServers": {
    "lnbits_agent_wallet_agent_name": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lnbits/lnbits-agent-wallet-mcp.git", "lnbits-agent-wallet-mcp"],
      "env": {
        "LNBITS_URL": "https://your-lnbits.example",
        "LNBITS_AGENT_TOKEN": "PASTE_RESTRICTED_ACL_BEARER_TOKEN_HERE",
        "LNBITS_AGENT_PROFILE_ID": "profile_id"
      }
    }
  }
}
```

Use a restricted token created for the agent. Rotate or delete the token to revoke runtime access.

## Security Notes

- Raw API token secrets are not stored by Agent Wallet.
- Runtime access is accepted only when the bearer token id matches the profile token id.
- Wallet ownership is checked when creating or updating profiles.
- LNURL callback URLs are validated before execution.
- Activity logs can contain request metadata supplied by the agent; do not send secrets in metadata, comments, or task ids.

## Powered by LNbits

[LNbits](https://lnbits.com) is a free and open-source lightning accounts system.

[![Visit LNbits Shop](https://img.shields.io/badge/Visit-LNbits%20Shop-7C3AED?logo=shopping-cart&logoColor=white&labelColor=5B21B6)](https://shop.lnbits.com/)
[![Try myLNbits SaaS](https://img.shields.io/badge/Try-myLNbits%20SaaS-2563EB?logo=lightning&logoColor=white&labelColor=1E40AF)](https://my.lnbits.com/login)
