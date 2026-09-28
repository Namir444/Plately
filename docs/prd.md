# Plately Product Requirements

## Product summary

Plately is a Django food discovery and ordering application. Customers can
create an account, search restaurants, explore menus, manage a simple cart, pay
through Razorpay, and revisit confirmed orders. A catalog administrator keeps
restaurant and menu listings current.

The product voice is warm, clear, and unhurried. Every page should help people
choose the next step without making food ordering feel like work.

## Users

- **Visitor:** discovers Plately and chooses to sign in or create an account.
- **Customer:** searches restaurants and cuisines, browses menus, manages a
  cart, checks out, and reviews paid orders.
- **Catalog administrator:** maintains restaurant details and menu items from
  the Plately dashboard.

## Product goals

1. Make restaurant discovery and menu browsing inviting and easy to scan.
2. Keep account, cart, checkout, and order-history screens visually consistent.
3. Give catalog administrators a direct workflow for creating, editing, and
   removing restaurants and menu items, plus a safe bulk-import option.
4. Confirm payment and save an order only after server-side verification.
5. Keep the existing Django package, app label, database tables, and migration
   history stable while the interface improves.

## Customer journeys

### Account access

Visitors can sign up with a username, password, email, mobile number, and
delivery address. New passwords are hashed with Django's password hashers.
Successful sign-in creates a server-side Django session. Existing plain-text
passwords are upgraded after a successful sign-in. The reserved `admin`
username leads to catalog administration; other signed-in customers land on
restaurant discovery.

### Discover restaurants and menus

Customers can search by restaurant name or cuisine, clear a search, open a
restaurant menu, and see dish descriptions, prices, and vegetarian labels.
Empty search results and empty menus explain what happened and provide a next
step.

### Cart and checkout

Customers can add menu items, remove items, review the total, and continue to
Razorpay Checkout. The cart currently stores items as a set, so each item can
appear once and quantity controls are not available. Checkout displays the
delivery details saved on the account and reports a useful state when the cart,
payment SDK, provider, or configuration is unavailable.

The server creates a pending order with item and delivery-address snapshots.
The payment callback is CSRF-protected. The server checks Razorpay's signature,
provider order ID, amount, INR currency, and captured status before it marks an
order paid and removes the purchased items from the cart.

### Order history

Customers can view paid orders and open a saved confirmation with line items,
total paid, and the delivery-address snapshot. Reading order history does not
change the cart.

### Catalog administration

The dashboard summarizes restaurant and menu counts. Administrators can add,
list, edit, and delete restaurant records; add, edit, and delete menu items; and
upload a CSV catalog. Imports validate before writing, update matching records,
and leave catalog entries absent from the file untouched. The dashboard links
to the supported CSV format; the same importer is available as a management
command with a dry-run option. Use restaurant supplied, licensed, or otherwise
authorized records. Destructive actions ask for a browser confirmation.

## Quality and interface requirements

- Use one responsive shared layout, a calm cream and terracotta palette, clear
  hierarchy, readable cards, and consistent buttons and form controls.
- Keep keyboard focus visible, label form controls, use semantic headings, and
  provide meaningful alternative text for catalog imagery.
- Format order prices in Indian rupees and keep payment totals in decimal form.
- Keep all state-changing forms POST-only and include CSRF tokens.
- Render user-entered values through Django's normal template escaping.

## Current limits

- The app uses its own session key tied to the legacy `Customer` model. The
  administrator role is still represented by the reserved `admin` username,
  not Django groups or staff permissions.
- Cart quantities, delivery tracking, courier assignment, inventory,
  cancellations, and refunds are not implemented.
- The checkout flow is designed for Razorpay test credentials; production use
  requires production credentials, deployment security settings, and payment
  capture configured in the Razorpay Dashboard.
- Legacy plain-text passwords remain until the corresponding accounts next
  sign in successfully.
