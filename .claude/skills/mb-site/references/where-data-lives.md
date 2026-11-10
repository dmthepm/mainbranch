# Where data lives

1. Code repos (app, site, tools): product code only. Never customer data, customers' customers' data, photos or videos. Tests, fixtures and screenshots use invented values in the real case's shape.
2. The business repo (the Main Branch hub): the team's private memory, team and agents only. Real material belongs there (recordings, P&L, reviews, real examples). No large customer datasets, because hub commits are never deleted.
3. The tracker: media and screen recordings on the issue they explain.
4. Production: customers' customers' data and sensitive categories (health, date of birth, ID photos, signatures, bank details), encrypted.
5. Direction rule for agents: real data flows up into the hub and the tracker, never down into a code repo. Going down, it becomes an invented example of the same shape.

## Going down: the same shape, invented values

- A phone number in a test uses an invented value such as `+1 202-555-0142` in the same format as the real case.
- A screenshot of a contact card uses invented names, phone numbers and images while keeping the layout and field shapes.

Source: maintainer direction, 19 October 2026.
