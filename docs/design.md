# Plately Design Notes

## Product voice

Plately is friendly, fresh, and relaxed. Keep copy short and specific: tell
people where they are, what they can do, and what happens next. Food language
can add warmth, but should not obscure prices, payment status, or errors.

The tagline is **“Good food. Good mood.”** Use Plately consistently in page
titles, navigation, account flows, checkout, and order confirmations.

## Visual direction

The interface uses soft cream surfaces, warm terracotta actions, charcoal
headings, and muted green for positive food and order states. Spacious cards,
gentle shadows, and rounded corners give the product a calm, welcoming feel.

| Role | Treatment |
| --- | --- |
| Page | Cream background with a subtle peach glow |
| Primary action | Terracotta fill with a darker hover state |
| Secondary action | White surface, quiet border, charcoal text |
| Main text | Warm charcoal with compact, confident headings |
| Supporting text | Muted brown-gray for descriptions and hints |
| Positive state | Muted green with a pale green background |
| Error state | Deep red with a pale warm-red surface |
| Surfaces | White cards, soft border, rounded corners, restrained shadow |

The design tokens and reusable styles live in
`delivery/static/FoodHub/styles.css`. Keep CSS grouped around shared page
patterns and add responsive behavior alongside those patterns.

## Page patterns

- **Landing:** welcoming hero with a clear sign-up action, an account sign-in
  action, and a few concise product benefits.
- **Account forms:** narrow, centered cards with short introductions, labeled
  fields, one clear submit action, and a route to the other account flow.
- **Restaurant discovery:** search controls, restaurant cards, cuisine and
  rating details, and distinct no-results feedback.
- **Menu browsing:** clear dish name, description, price, dietary marker, image,
  and a direct add-to-cart action.
- **Cart and checkout:** itemized amounts, a prominent total, delivery details,
  and clear navigation to continue or return.
- **Catalog management:** dashboard counts, restaurant cards, directly editable
  menu entries, validated forms, CSV import controls, and confirmation before
  destructive actions.
- **Orders and payment states:** clear paid/pending language, saved details,
  accessible status cues, and a useful next step.

## Interaction and accessibility

- Keep every action keyboard reachable and show a strong focus indicator.
- Use actual labels and semantic buttons for actions; links navigate.
- Do not communicate success, dietary status, or errors through color alone.
- Give meaningful images descriptive alt text; mark decorative shapes hidden
  from assistive technology.
- Keep content readable at narrow widths without horizontal page scrolling.
- Display money consistently as Indian rupees and distinguish pending payment
  from a confirmed order.

## Implemented scope

Every product page extends `delivery/base.html` and shares the Plately
navigation, message area, footer, and stylesheet. Responsive customer and
administrator screens include empty states, restaurant search, menu editing,
cart removal, order summaries, and payment feedback.
