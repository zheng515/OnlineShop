# Online Shopping Website — Functional Requirements

> **Revision notes**
> - **Rev. 2** clarified requirements that were previously open to interpretation. Requirement numbers
>   FR1–FR35 are unchanged; clarifications are added to the existing requirements, and rules that apply
>   across several requirements are collected in Section 7 (FR36–FR40).
> - **Rev. 3** adds order placement and order management (Section 8, FR41–FR50). Stock is now deducted
>   when an order is placed. FR4, FR5, FR11, FR14, FR29, FR32, FR35 and FR38 are updated accordingly.
>   Payment processing remains out of scope.

## 1. Login and Access Control

**FR1 — Role Selection**  
The system shall provide a login page where visitors can select either **Administrator Login** or **Customer Login**. Customer Login shall be selected by default. A user who is already logged in and opens the login page shall be redirected to the home page of their role (see FR4).

**FR2 — User Authentication**  
The system shall authenticate administrators and customers using their assigned account credentials. The system shall display an error message when the supplied credentials are invalid.  
- Credentials are valid only when the username exists, the password matches, **and** the account's role matches the selected login option. An administrator account used with Customer Login, or a customer account used with Administrator Login, shall be rejected as invalid credentials.  
- The error message shall not reveal whether the username, the password or the role was wrong (e.g. "Invalid username or password for Customer Login.").  
- If the username or password is left empty, the system shall ask the user to enter it without attempting authentication.

**FR3 — Preconfigured Customer Accounts**  
The system shall support preconfigured customer accounts for this version. Customer self-registration shall not be provided.  
- All accounts (administrator and customer) are created by the system on first start-up; at least one administrator account and one customer account shall exist.  
- No function to register, create, edit or delete accounts shall be provided in the user interface.  
- Passwords shall be stored only in hashed form.

**FR4 — Role-Based Redirection**  
After successful authentication, the system shall redirect administrators to the Product Management page and customers to the Product Browsing page. Administrators can reach the Order Management page (FR49) from the navigation bar; customers can reach the Shopping Cart and My Orders (FR46).

**FR5 — Role-Based Access Control**  
The system shall restrict product management functions to authenticated administrators and shopping functions to authenticated customers. Order management is restricted to administrators, and each customer can see and act on only their own orders (FR50).  
- Access control shall be enforced on the server for every request, not only in the user interface.  
- A user who is not logged in, or whose session has expired (FR36), and who opens any page other than the login page shall be returned to the login page.  
- A logged-in user who opens a page belonging to the other role shall be redirected to the home page of their own role.

**FR6 — Logout**  
The system shall allow authenticated users to log out and return to the login page. Logging out shall invalidate the session on the server, so the session can no longer be used.

## 2. Administrator — Product Management

**FR7 — View Product List**  
The system shall allow administrators to view a list of existing products, including each product's image, name, price, and stock quantity for each available size.  
- The list shall have one column for each of the sizes S, M, L and XL. A size the product does not offer shall be shown as "—"; a size with zero stock shall be highlighted.  
- Products shall be listed with the most recently added first.  
- When there are no products, the system shall display a message saying so.

**FR8 — Add Product**  
The system shall allow administrators to add a product by providing its image, name, price, and stock quantities for one or more sizes selected from **S, M, L, and XL**. A size is offered by ticking it and entering its stock quantity; an offered size may have a stock quantity of zero.

**FR9 — View Product Details**  
The system shall allow administrators to view the complete information of an existing product, including its image, name, price, available sizes, and size-specific stock quantities. The details shall also show the total stock and the time of the last update, and indicate which sizes are out of stock.

**FR10 — Update Product**  
The system shall allow administrators to update an existing product's image, name, price, available sizes, and stock quantities for each size.  
- Choosing a new image is optional when updating; if none is chosen, the current image is kept.  
- Unticking a size removes that size from the product. Cart entries for a removed size are handled as described in FR34.  
- Changes take effect immediately for all customers, including items already in carts (FR25, FR30).

**FR11 — Delete Product**  
The system shall allow administrators to delete an existing product after confirming the deletion.  
- The confirmation dialog shall name the product and state that the action cannot be undone. Cancelling shall leave the product unchanged.  
- Deleting a product also deletes its image file, unless the image is still shown in an existing order (FR45). Cart entries for the deleted product are handled as described in FR34.  
- Deleting a product shall not change or remove existing orders that contain it (FR45).

**FR12 — Search Products in Management**  
The system shall allow administrators to search for products by keyword in the Product Management page. The search shall use the same matching rules as the customer search (FR16): case-insensitive matching of the keyword anywhere in the product name. An empty keyword shall show all products. The system shall show the number of matches, or a message when no products match, and shall provide a way to clear the search.

**FR13 — Validate Product Information**  
The system shall validate product information before saving. The product name and image shall be required, the price shall be greater than zero, each size-specific stock quantity shall be a non-negative integer, and sizes shall be limited to **S, M, L, and XL**. At least one size shall be available for a product. In detail:  
- **Name:** leading and trailing spaces are removed; the result must be 1–100 characters long.  
- **Price:** a number greater than 0 and not greater than 1,000,000, with at most two decimal places.  
- **Stock:** a whole number from 0 to 1,000,000 for each offered size.  
- **Sizes:** only S, M, L and XL; at least one size must be offered. A size with zero stock counts as offered.  
- **Image:** required when adding a product; optional when updating (FR10).  
- Validation shall be performed by the server for every save, whether or not the browser has already checked the input. All problems found shall be reported together, and nothing shall be saved while any problem remains.

**FR14 — Handle Product Images**  
The system shall allow administrators to upload or replace a product image and shall display an error message if the image cannot be uploaded or does not meet the supported image format requirements.  
- Supported formats are **JPEG, PNG, GIF and WEBP**. The format shall be determined from the file's actual contents, not from its file name or extension. Other formats, including SVG, shall be rejected.  
- The maximum file size is **5 MB**. Empty files shall be rejected.  
- The form shall show a preview of the selected image before saving.  
- When an image is replaced, the previous image file shall be deleted after the product has been saved successfully, unless it is still shown in an existing order (FR45). If saving fails, the product shall keep its previous image.

## 3. Customer — Product Browsing and Search

**FR15 — Browse Products**  
The system shall display a list of products to customers, showing each product's image, name, and price.  
- Products shall be listed with the most recently added first.  
- A product that is out of stock in every size shall still be displayed, marked "Out of stock".

**FR16 — Search Products**  
The system shall allow customers to search for products using keywords matched against product names. The search shall be case-insensitive, and the system shall display matching results or a message when no products match.  
- A product matches when the keyword (with leading and trailing spaces removed) appears anywhere in its name.  
- An empty keyword shall show all products.  
- When no products match, the system shall offer a way to show all products again.

**FR17 — View Product Details**  
The system shall allow customers to select a product and open its detail page. The page shall display the product image, name, price, available sizes, and stock quantity for each size. If the product no longer exists, the page shall say that the product is no longer available.

**FR18 — Select Product Size**  
The system shall allow customers to select one available size from **S, M, L, and XL** before adding a product to the cart or purchasing it directly. Sizes with no stock shall not be selectable for purchase.  
- All four sizes shall be shown. A size the product does not offer shall be labelled "Not offered", and a size with zero stock shall be labelled "Out of stock"; neither can be selected.  
- No size is selected when the page opens. **Add to Cart** and **Buy Now** shall be unavailable until a size with stock is selected.  
- The quantity defaults to 1. A quantity above the stock of the selected size cannot be added to the cart or purchased.

## 4. Customer — Shopping Cart

**FR19 — Add to Cart**  
The system shall allow customers to add a product with a selected size and quantity to their shopping cart, provided sufficient stock is available. The requested quantity shall be a positive integer.  
- "Sufficient stock" means that the quantity already in the cart for that product and size, plus the requested quantity, does not exceed the current stock for that size.  
- Each customer has one cart. It is stored on the server, belongs to the customer's account, and is kept after logout.  
- Adding an item to the cart does **not** reserve stock (FR38).

**FR20 — Handle Duplicate Cart Items**  
When a customer adds the same product in the same size more than once, the system shall combine the items into one cart entry and update its quantity. If the combined quantity would exceed the available stock, the request shall be rejected, the existing entry shall stay unchanged, and the message shall state both the available stock and the quantity already in the cart.

**FR21 — View Shopping Cart**  
The system shall allow customers to view their cart items, including each product's image, name, selected size, quantity, unit price, and subtotal, as well as the total cart price. Items with a problem (FR29, FR33, FR34) shall be highlighted with a message explaining the problem.

**FR22 — Update Cart Quantity**  
The system shall allow customers to change the quantity of a cart item. The new quantity shall be a positive integer and shall not exceed the available stock for the selected size. An invalid quantity shall be rejected with a message, and the item shall keep its previous quantity. The quantity of an unavailable item (FR34) cannot be changed; such an item can only be removed.

**FR23 — Remove Cart Items**  
The system shall allow customers to remove individual items from their shopping cart.

**FR24 — Handle Empty Cart**  
The system shall display an appropriate message and shall not allow customers to proceed to checkout when the shopping cart is empty. The server shall also report an empty cart as not valid for checkout.

**FR25 — Recalculate Cart Prices**  
The system shall calculate each cart item's subtotal as the current unit price multiplied by its quantity, and calculate the cart total as the sum of all item subtotals. The system shall use the current product price when displaying the cart and checkout summary.  
- An unavailable item (FR34) has no unit price or subtotal and is not included in the total.  
- Amounts are calculated as described in FR37.

**FR26 — Proceed to Checkout from Cart**  
The system shall allow customers to proceed from a non-empty shopping cart to the Checkout page with all cart items and their selected sizes and quantities. Proceeding is only possible when **every** item in the cart can be purchased (see FR29 and FR34). The cart shall be refreshed with current data when the customer chooses to proceed.

## 5. Customer — Direct Purchase and Checkout

**FR27 — Buy Now**  
The system shall allow customers to select a size and quantity on a product detail page and proceed directly to the Checkout page without adding the product to the shopping cart. The same size and quantity rules as for Add to Cart apply (FR18, FR19). Buy Now shall not change the contents of the cart.

**FR28 — Display Checkout Summary**  
The system shall display all items selected for checkout, including product names, images, sizes, quantities, unit prices, subtotals, and the total amount payable. The same summary format shall be used for cart checkout and direct purchase.

**FR29 — Validate Stock at Checkout**  
The system shall revalidate the requested quantity against the current stock for each selected size before allowing the customer to continue. If stock is insufficient or a product is no longer available, the system shall notify the customer and identify the affected item.  
- Revalidation shall take place when the Checkout page opens, when the customer chooses **Continue to Payment**, when the Payment page opens, and once more when the order is placed (FR41).  
- An item has a problem when its product has been deleted, its size is no longer offered, its size is out of stock, or the requested quantity exceeds the current stock. The message shall name the product and size and, for insufficient stock, state the quantity available.  
- While **any** item has a problem, the customer shall not be able to continue. Partial checkout of only the valid items is not provided; the customer must return to the cart or product page to remove or adjust the affected items (FR31).

**FR30 — Handle Price Changes**  
If a product's price changes after it has been added to the cart, the system shall use the current price in the cart and checkout summary and recalculate the relevant subtotals and total.

**FR31 — Return from Checkout**  
The system shall allow customers to return from the Checkout page to the shopping cart or product detail page to revise their selections. Cart checkout returns to the shopping cart; direct purchase returns to the product detail page with the previously selected size and quantity already filled in, provided the size is still in stock (the quantity is reduced to the available stock if necessary). The Payment page shall offer a way back to the Checkout page.

**FR32 — Payment Page and Scope Limitation**  
The system shall provide a checkout/payment page for both cart checkout and direct purchase, displaying the order summary and total amount. Actual payment methods, payment processing and payment confirmation shall not be implemented in this version. Order placement and order status tracking are specified in Section 8; physical fulfilment (shipping, delivery) happens outside the system and is only recorded through order statuses (FR47).  
- The Payment page shall state clearly that online payment is not available in this version and that no payment will be taken. It shall provide a **Place Order** button (FR41).  
- Visiting the Checkout or Payment page shall not create an order or change stock quantities or cart contents; only placing the order does (FR41).

## 6. Availability and Error Handling

**FR33 — Handle Out-of-Stock Products**  
The system shall prevent customers from purchasing a size whose stock quantity is zero. The system may continue to display the product, but it shall clearly indicate that the size is out of stock. This shall be enforced by the server when adding to the cart, updating cart quantities and building the checkout summary, not only in the user interface.

**FR34 — Handle Deleted or Unavailable Products**  
If a product in a customer's cart becomes unavailable or is deleted before checkout, the system shall notify the customer and prevent that item from being checked out.  
- A cart item is **unavailable** when its product has been deleted or its size has been removed from the product (FR10).  
- Unavailable items shall remain in the cart, showing the product name as it was when the item was added, so the customer can see what changed. They shall be marked as unavailable with an explanation, and have no price (FR25).  
- As long as an unavailable item remains in the cart, checkout of the cart is blocked (FR29); the customer must remove it.

**FR35 — Provide Feedback for Invalid Actions**  
The system shall display a clear message when an operation cannot be completed, including invalid product information, unavailable stock, failed image upload, invalid login credentials, an unsuccessful product search, an order that cannot be placed, or an order status change that is not allowed. Where several problems are found at once (e.g. in product validation), all of them shall be listed together. Successful actions (adding, updating or deleting a product, adding to or removing from the cart, placing, cancelling or updating an order) shall also be confirmed with a short message.

## 7. General Rules

**FR36 — Sessions**  
A login session shall be valid for **8 hours** from the time of login, after which the user must log in again (FR5). A session ends earlier if the user logs out (FR6).

**FR37 — Prices and Currency**  
The shop uses a single currency. All prices, subtotals and totals shall be displayed with exactly two decimal places and calculated without rounding errors (e.g. in whole cents).

**FR38 — Stock Reservation and Deduction**  
Stock shall not be reserved when items are added to the cart, when Buy Now is used, or while the customer is on the Checkout or Payment page. Several customers may therefore hold the same item in their carts; availability is checked again at checkout (FR29) and when the order is placed (FR41). Stock quantities change only:  
- when an administrator updates a product (FR10);  
- when an order is placed — the ordered quantities are deducted (FR41);  
- when an order is cancelled — the ordered quantities are added back (FR48).

**FR39 — Initial Data**  
On first start-up the system may create a set of demo products. Demo products shall be created only once: products deleted by an administrator shall not be re-created when the system is restarted.

**FR40 — Server-Side Enforcement**  
All rules in this document that restrict input or actions (access control, product validation, size and stock limits, quantity rules) shall be enforced by the server. Checks in the browser are only for faster feedback and shall not be relied on.

## 8. Orders

**FR41 — Place Order**  
The system shall allow customers to place an order from the Payment page, for both cart checkout and direct purchase.  
- When the customer chooses **Place Order**, the server shall revalidate every item against the current stock and prices (FR29) and, if everything is valid, in **one indivisible operation**: deduct the ordered quantity from the stock of each product size, create the order with status **Placed** (FR47), and — for cart checkout — remove the ordered items from the cart. Direct purchase (Buy Now) shall not change the cart.  
- Either all of this happens or none of it does. If any item is invalid, no order is created, no stock is changed, and the customer is shown the affected items (FR29).  
- After a successful order, the customer shall be shown a confirmation page with the order number and the order details (FR45).  
- Payment is not taken (FR32). The confirmation shall say that the order has been placed and that no payment has been charged.

**FR42 — Confirm the Amount Payable**  
The order shall be created only for the total amount that was displayed to the customer when they chose **Place Order**. If the current total differs (for example because a price changed after the Payment page was opened), the order shall not be placed; the customer shall be told that prices have changed and shown the updated summary to confirm again.

**FR43 — Prevent Duplicate Orders**  
Submitting the same order more than once (for example by clicking **Place Order** twice, or a network retry) shall create only one order. A repeated submission shall lead to the confirmation of the order already placed. Opening the Payment page again later and placing a new order is a new order.

**FR44 — Concurrent Orders**  
Stock shall never become negative. When several customers order the same product size at the same time and the stock is not enough for all of them, only the orders that the remaining stock can satisfy shall be placed; the others shall fail with the message described in FR29.

**FR45 — Order Record**  
Each order shall record: a unique order number, the customer, the date and time it was placed, its source (cart or direct purchase), its current status and status history (FR47), and for each item the product name, image, size, unit price, quantity and subtotal, plus the order total.  
- Item details are a record of what was ordered. They shall be stored as they were when the order was placed and shall not change if the product is later updated or deleted.  
- The order number is shown as `#` followed by six digits, e.g. `#000042`.

**FR46 — Customer Order History**  
The system shall provide a **My Orders** page listing the customer's orders, most recent first, showing for each order its number, date, status, number of items and total. Selecting an order shall open its detail page showing all information in FR45. A message shall be shown when the customer has no orders.

**FR47 — Order Statuses**  
An order has one of the statuses **Placed**, **Shipped**, **Completed** or **Cancelled**. Only these changes are allowed:  

| From    | To        | Who                       |
|---------|-----------|---------------------------|
| Placed  | Shipped   | Administrator             |
| Shipped | Completed | Administrator             |
| Placed  | Cancelled | Administrator or the customer who placed the order |

Any other change shall be rejected with a message. Every status change shall be recorded in the order's status history with the new status, the date and time, and who made the change; the history shall be shown on the order detail pages.

**FR48 — Cancel Order**  
An order can be cancelled only while its status is **Placed** (FR47). The system shall ask for confirmation before cancelling.  
- On cancellation the ordered quantities shall be added back to the stock of each product size, in the same indivisible operation as the status change.  
- If a product has since been deleted, or the size is no longer offered, no stock is added back for that item; the cancellation still succeeds.  
- Cancelled orders remain in the order history.

**FR49 — Order Management (Administrator)**  
The system shall provide an **Order Management** page for administrators that:  
- lists all orders, most recent first, with order number, customer, date, status, number of items and total;  
- can be filtered by status and searched by a keyword matched (case-insensitively) against the order number and the customer's username or display name, with a message when nothing matches;  
- opens the details of an order (FR45) including the customer and status history;  
- lets the administrator change the status as allowed by FR47, with a confirmation before cancelling.

**FR50 — Order Access Control**  
Customers shall be able to view and cancel only their own orders; an order that belongs to another customer shall be treated as not found. Administrators can view and manage all orders but cannot place orders. These rules shall be enforced by the server (FR40).
