# V2 anonymous guest launch

Status: in progress

## Contract

Confirmed guest payment on a V2 workstation creates a durable one-time access
grant. The assigned Linux/Windows client redeems it through a device-authenticated
V2 RPC, verifies the signed guest payload, persists a local guest ledger, and
opens the access gate. Redemption is idempotent and never calls the V1 session
endpoint.

## Acceptance criteria

- [ ] payment confirmation can prepare a V2 guest grant;
- [ ] redemption creates `v2_guest_local_ledger` and returns a signed payload;
- [ ] replay returns the same active grant/session;
- [ ] the client persists and consumes guest minutes locally;
- [ ] stop uses the guest RPC and does not emit client-profile facts;
- [ ] focused backend/frontend/client tests pass; Linux proof remains separate
  from native Windows proof.
