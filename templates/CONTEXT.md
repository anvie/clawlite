# CONTEXT.md — Domain Knowledge

Project and business context for the agent.

## Project

*Describe the project or business:*

```markdown
- **Name:** [Project/Business Name]
- **Type:** [e.g., E-commerce, SaaS, Consulting]
- **Location:** [If relevant]
```

## External Systems

*Document connected services:*

```markdown
### ERP System
- URL: https://erp.example.com
- API: REST, auth via token
- Purpose: Invoicing, inventory

### Payment Gateway
- Provider: Stripe
- Currencies: USD, IDR
```

## Terminology

*Define domain-specific terms:*

```markdown
- **SKU:** Stock Keeping Unit
- **PO:** Purchase Order
- **Lead:** Potential customer
```

## Business Rules

*Important rules the agent should follow:*

```markdown
- Weekday pricing: Mon-Thu
- Weekend pricing: Fri-Sun
- Minimum order: 100 units
```

## Key Contacts

*People the agent might need to reference:*

```markdown
- **Finance:** finance@example.com
- **Support:** support@example.com
```

---

*Add your domain-specific knowledge here. This file is shared across all users.*
