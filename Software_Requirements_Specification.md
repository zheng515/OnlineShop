# Online Shopping Website — Functional Requirements

> **Revision notes**
> - **Rev. 2** clarified requirements that were previously open to interpretation. Requirement numbers
>   FR1–FR35 are unchanged; clarifications are added to the existing requirements, and rules that apply
>   across several requirements are collected in Section 7 (FR36–FR40).
> - **Rev. 3** adds order placement and order management (Section 8, FR41–FR50). Stock is now deducted
>   when an order is placed. FR4, FR5, FR11, FR14, FR29, FR32, FR35 and FR38 are updated accordingly.
>   Payment processing remains out of scope.
> - **Rev. 4** adds security requirements (Section 9, FR51–FR59): cookie-based sessions, CSRF
>   protection, login throttling, account and password rules, security headers, HTTPS, request size
>   limits, error handling and security logging. FR2, FR3, FR6 and FR36 are updated accordingly.
> - **Rev. 5** extends the product catalogue (Section 10, FR60–FR67): categories, descriptions,
>   multiple images per product, pagination, sorting and filtering. FR7–FR17 and FR45 are updated
>   accordingly.
> - **Rev. 6** adds deployment, data management and quality requirements (Section 11, FR68–FR77):
>   PostgreSQL support, versioned schema migrations, configuration, container deployment, health
>   checks, backups, automated tests in a browser, code checks and continuous integration.
> - **Rev. 7** adds online payment (Section 12, FR78–FR87) through a built-in **mock payment
>   provider** that behaves like a real one but moves no money. Orders now wait for payment, and
>   unpaid orders are cancelled automatically when their payment deadline passes. FR32, FR38, FR41,
>   FR43, FR46, FR47, FR48 and FR49 are updated accordingly.

## 1. Login and Access Control

**FR1 — Role Selection**  
The system shall provide a login page where visitors can select either **Administrator Login** or **Customer Login**. Customer Login shall be selected by default. A user who is already logged in and opens the login page shall be redirected to the home page of their role (see FR4).

**FR2 — User Authentication**  
The system shall authenticate administrators and customers using their assigned account credentials. The system shall display an error message when the supplied credentials are invalid.  
- Credentials are valid only when the username exists, the password matches, **and** the account's role matches the selected login option. An administrator account used with Customer Login, or a customer account used with Administrator Login, shall be rejected as invalid credentials.  
- The error message shall not reveal whether the username, the password or the role was wrong (e.g. "Invalid username or password for Customer Login.").  
- If the username or password is left empty, the system shall ask the user to enter it without attempting authentication.  
- Repeated failed attempts are throttled as described in FR53.

**FR3 — Preconfigured Customer Accounts**  
The system shall support preconfigured customer accounts for this version. Customer self-registration shall not be provided.  
- Accounts (administrator and customer) are created and maintained by an operator with a server-side account command, not through the web interface (FR54). For local development and demonstrations, a set of demo accounts may be created on first start-up (FR54).  
- No function to register, create, edit or delete accounts shall be provided in the user interface.  
- Passwords shall be stored only in hashed form, using a slow, salted password-hashing function.

**FR4 — Role-Based Redirection**  
After successful authentication, the system shall redirect administrators to the Product Management page and customers to the Product Browsing page. Administrators can reach the Order Management page (FR49) from the navigation bar; customers can reach the Shopping Cart and My Orders (FR46).

**FR5 — Role-Based Access Control**  
The system shall restrict product management functions to authenticated administrators and shopping functions to authenticated customers. Order management is restricted to administrators, and each customer can see and act on only their own orders (FR50).  
- Access control shall be enforced on the server for every request, not only in the user interface.  
- A user who is not logged in, or whose session has expired (FR36), and who opens any page other than the login page shall be returned to the login page.  
- A logged-in user who opens a page belonging to the other role shall be redirected to the home page of their own role.

**FR6 — Logout**  
The system shall allow authenticated users to log out and return to the login page. Logging out shall invalidate the session on the server, so the session can no longer be used, and remove the session cookie from the browser (FR51).

## 2. Administrator — Product Management

**FR7 — View Product List**  
The system shall allow administrators to view a list of existing products, including each product's main image (FR62), name, category (FR60), price, and stock quantity for each available size.  
- The list shall have one column for each of the sizes S, M, L and XL. A size the product does not offer shall be shown as "—"; a size with zero stock shall be highlighted.  
- Products shall be listed with the most recently added first unless another order is chosen (FR64). The list is divided into pages of **20** products (FR63) and can be filtered by category (FR65).  
- When there are no products, the system shall display a message saying so.

**FR8 — Add Product**  
The system shall allow administrators to add a product by providing its images (FR62), name, price, an optional description (FR61), an optional category (FR60), and stock quantities for one or more sizes selected from **S, M, L, and XL**. A size is offered by ticking it and entering its stock quantity; an offered size may have a stock quantity of zero.

**FR9 — View Product Details**  
The system shall allow administrators to view the complete information of an existing product, including all its images (the main image first), name, price, category, description, available sizes, and size-specific stock quantities. The details shall also show the total stock and the time of the last update, and indicate which sizes are out of stock.

**FR10 — Update Product**  
The system shall allow administrators to update an existing product's images, name, price, description, category, available sizes, and stock quantities for each size.  
- Images can be added, removed and reordered (FR62); images that are not changed are kept.  
- Unticking a size removes that size from the product. Cart entries for a removed size are handled as described in FR34.  
- Changes take effect immediately for all customers, including items already in carts (FR25, FR30).

**FR11 — Delete Product**  
The system shall allow administrators to delete an existing product after confirming the deletion.  
- The confirmation dialog shall name the product and state that the action cannot be undone. Cancelling shall leave the product unchanged.  
- Deleting a product also deletes its image files, except images still shown in an existing order (FR45). Cart entries for the deleted product are handled as described in FR34.  
- Deleting a product shall not change or remove existing orders that contain it (FR45).

**FR12 — Search Products in Management**  
The system shall allow administrators to search for products by keyword in the Product Management page, using the same matching rules as the customer search (FR16). An empty keyword shall show all products. The system shall show the number of matches, or a message when no products match, and shall provide a way to clear the search. Search can be combined with the category filter, sorting and pagination (FR63–FR65).

**FR13 — Validate Product Information**  
The system shall validate product information before saving. The product name and at least one image shall be required, the price shall be greater than zero, each size-specific stock quantity shall be a non-negative integer, and sizes shall be limited to **S, M, L, and XL**. At least one size shall be available for a product. In detail:  
- **Name:** leading and trailing spaces are removed; the result must be 1–100 characters long.  
- **Price:** a number greater than 0 and not greater than 1,000,000, with at most two decimal places.  
- **Stock:** a whole number from 0 to 1,000,000 for each offered size.  
- **Sizes:** only S, M, L and XL; at least one size must be offered. A size with zero stock counts as offered.  
- **Images:** 1–8 images (FR62). Each must be an image uploaded for this product or a newly uploaded image not yet attached to any product.  
- **Description:** optional; at most 2,000 characters (FR61).  
- **Category:** optional; if given, it must be an existing category (FR60).  
- Validation shall be performed by the server for every save, whether or not the browser has already checked the input. All problems found shall be reported together, and nothing shall be saved while any problem remains.

**FR14 — Handle Product Images**  
The system shall allow administrators to upload, replace, remove and reorder product images (FR62) and shall display an error message if an image cannot be uploaded or does not meet the supported image format requirements.  
- Supported formats are **JPEG, PNG, GIF and WEBP**. The format shall be determined from the file's actual contents, not from its file name or extension. Other formats, including SVG, shall be rejected.  
- The maximum file size is **5 MB** per image. Empty files shall be rejected.  
- Each image is uploaded in its own request as soon as it is selected, so the 6 MB request limit (FR57) is never exceeded. The form shall show each uploaded image before saving and report a failed upload for that image only.  
- An uploaded image becomes part of the product only when the product is saved. Uploaded images that are not attached to a product within **24 hours** shall be deleted.  
- Images removed from a product shall be deleted after the product has been saved successfully, unless they are still shown in an existing order (FR45). If saving fails, the product keeps its previous images.

## 3. Customer — Product Browsing and Search

**FR15 — Browse Products**  
The system shall display a list of products to customers, showing each product's main image, name, and price.  
- Products shall be listed with the most recently added first unless another order is chosen (FR64), in pages of **12** products (FR63).  
- Customers can narrow the list by category, price range, size and availability (FR65).  
- A product that is out of stock in every size shall still be displayed, marked "Out of stock", unless the customer chooses to see only products in stock.

**FR16 — Search Products**  
The system shall allow customers to search for products using keywords matched against product names and descriptions. The search shall be case-insensitive, and the system shall display matching results or a message when no products match.  
- A product matches when the keyword (with leading and trailing spaces removed) appears anywhere in its name or description. Case-insensitive matching shall also work for non-English letters.  
- An empty keyword shall show all products.  
- Search can be combined with filters, sorting and pagination (FR63–FR65).  
- When no products match, the system shall offer a way to show all products again.

**FR17 — View Product Details**  
The system shall allow customers to select a product and open its detail page. The page shall display the product's images (FR62), name, price, category, description, available sizes, and stock quantity for each size. If the product no longer exists, the page shall say that the product is no longer available.  
- The main image is shown large; the other images are shown as thumbnails that display the chosen image large when selected.  
- The category is a link to the product list filtered by that category (FR65).

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

**FR32 — Payment Page**  
The system shall provide a checkout/payment page for both cart checkout and direct purchase, displaying the order summary and the total amount payable, with a **Place Order and Pay** button that places the order (FR41) and takes the customer to the payment provider (FR78). Physical fulfilment (shipping, delivery) happens outside the system and is only recorded through order statuses (FR47).  
- While the mock payment provider is in use (FR84), the page shall state that payments are test payments and that no real money is charged.  
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
A login session shall be valid for **8 hours** from the time of login, after which the user must log in again (FR5). A session ends earlier if the user logs out (FR6) or the account's password is changed (FR54). Sessions are handled as described in FR51.

**FR37 — Prices and Currency**  
The shop uses a single currency. All prices, subtotals and totals shall be displayed with exactly two decimal places and calculated without rounding errors (e.g. in whole cents).

**FR38 — Stock Reservation and Deduction**  
Stock shall not be reserved when items are added to the cart, when Buy Now is used, or while the customer is on the Checkout or Payment page. Several customers may therefore hold the same item in their carts; availability is checked again at checkout (FR29) and when the order is placed (FR41). Stock quantities change only:  
- when an administrator updates a product (FR10);  
- when an order is placed — the ordered quantities are deducted and held for the order while it awaits payment (FR41, FR79);  
- when an order is cancelled, by the customer, an administrator or because its payment deadline passed — the ordered quantities are added back (FR48, FR79).

**FR39 — Initial Data**  
On first start-up the system may create a set of demo products. Demo products shall be created only once: products deleted by an administrator shall not be re-created when the system is restarted.

**FR40 — Server-Side Enforcement**  
All rules in this document that restrict input or actions (access control, product validation, size and stock limits, quantity rules) shall be enforced by the server. Checks in the browser are only for faster feedback and shall not be relied on.

## 8. Orders

**FR41 — Place Order**  
The system shall allow customers to place an order from the Payment page, for both cart checkout and direct purchase.  
- When the customer chooses **Place Order**, the server shall revalidate every item against the current stock and prices (FR29) and, if everything is valid, in **one indivisible operation**: deduct the ordered quantity from the stock of each product size, create the order with status **Awaiting payment** and a payment deadline (FR47, FR79), and — for cart checkout — remove the ordered items from the cart. Direct purchase (Buy Now) shall not change the cart.  
- Either all of this happens or none of it does. If any item is invalid, no order is created, no stock is changed, and the customer is shown the affected items (FR29).  
- After the order has been created, the customer shall be taken to the payment provider to pay (FR78). If the customer does not pay right away, the order stays in **My Orders** with a **Pay now** button until its payment deadline (FR79, FR80).  
- The order becomes **Paid** only when the payment provider confirms the payment (FR78, FR81).

**FR42 — Confirm the Amount Payable**  
The order shall be created only for the total amount that was displayed to the customer when they chose **Place Order**. If the current total differs (for example because a price changed after the Payment page was opened), the order shall not be placed; the customer shall be told that prices have changed and shown the updated summary to confirm again.

**FR43 — Prevent Duplicate Orders**  
Submitting the same order more than once (for example by clicking **Place Order** twice, or a network retry) shall create only one order. A repeated submission shall lead to the order already placed (and to its payment, if it is still awaiting payment). Opening the Payment page again later and placing a new order is a new order.

**FR44 — Concurrent Orders**  
Stock shall never become negative. When several customers order the same product size at the same time and the stock is not enough for all of them, only the orders that the remaining stock can satisfy shall be placed; the others shall fail with the message described in FR29.

**FR45 — Order Record**  
Each order shall record: a unique order number, the customer, the date and time it was placed, its source (cart or direct purchase), its current status and status history (FR47), and for each item the product name, main image (FR62), size, unit price, quantity and subtotal, plus the order total.  
- Item details are a record of what was ordered. They shall be stored as they were when the order was placed and shall not change if the product is later updated or deleted.  
- The order number is shown as `#` followed by six digits, e.g. `#000042`.

**FR46 — Customer Order History**  
The system shall provide a **My Orders** page listing the customer's orders, most recent first, showing for each order its number, date, status, number of items and total. Orders awaiting payment shall show the time left to pay (FR86). Selecting an order shall open its detail page showing all information in FR45. A message shall be shown when the customer has no orders.

**FR47 — Order Statuses**  
An order has one of the statuses **Awaiting payment**, **Paid**, **Shipped**, **Completed** or **Cancelled**. Only these changes are allowed:  

| From             | To        | Who |
|------------------|-----------|-----|
| Awaiting payment | Paid      | The system, when the payment provider confirms payment (FR78) |
| Awaiting payment | Cancelled | The customer who placed the order, an administrator, or the system when the payment deadline passes (FR79) |
| Paid             | Shipped   | Administrator |
| Paid             | Cancelled | The customer who placed the order, or an administrator; the payment is refunded (FR82) |
| Shipped          | Completed | Administrator |

Any other change shall be rejected with a message. Each change shall take effect only if the order is still in the expected status at that moment, so that two simultaneous changes (for example a payment confirmation and a cancellation) cannot both succeed. Every status change shall be recorded in the order's status history with the new status, the date and time, and who made the change (the customer, an administrator, or the system); the history shall be shown on the order detail pages.

**FR48 — Cancel Order**  
An order can be cancelled only while its status is **Awaiting payment** or **Paid** (FR47). The system shall ask for confirmation before cancelling; for a paid order the confirmation shall say that the amount paid will be refunded.  
- On cancellation the ordered quantities shall be added back to the stock of each product size, in the same indivisible operation as the status change.  
- If a product has since been deleted, or the size is no longer offered, no stock is added back for that item; the cancellation still succeeds.  
- Cancelling a paid order starts a full refund (FR82).  
- Cancelled orders remain in the order history.

**FR49 — Order Management (Administrator)**  
The system shall provide an **Order Management** page for administrators that:  
- lists all orders, most recent first, with order number, customer, date, status, number of items and total;  
- can be filtered by status and searched by a keyword matched (case-insensitively) against the order number and the customer's username or display name, with a message when nothing matches;  
- opens the details of an order (FR45) including the customer, status history, payment attempts and refunds (FR83);  
- lets the administrator change the status as allowed by FR47, with a confirmation before cancelling, and retry a failed refund (FR82).

**FR50 — Order Access Control**  
Customers shall be able to view and cancel only their own orders; an order that belongs to another customer shall be treated as not found. Administrators can view and manage all orders but cannot place orders. These rules shall be enforced by the server (FR40).

## 9. Security

**FR51 — Session Cookies**  
After a successful login, the server shall identify the session with a random, unguessable session identifier sent only in a cookie.  
- The cookie shall be marked **HttpOnly** (not readable by page scripts) and **SameSite=Lax**, and **Secure** when the site is served over HTTPS (FR56). Its lifetime shall match the session lifetime (FR36).  
- The session identifier shall not appear in response bodies, URLs, browser storage or logs, and the server shall accept it only from this cookie.  
- The server shall store only a one-way hash of the session identifier, so a copy of the database cannot be used to take over sessions.  
- A new session identifier shall be issued at every login; an identifier from before the login shall never be reused.

**FR52 — Cross-Site Request Forgery Protection**  
- Every state-changing request (one that creates, changes or deletes data) made with a session shall carry the session's anti-forgery token in a request header. The token is issued with the session, in a cookie that page scripts can read. Requests with a missing or wrong token shall be rejected, and the user shall be asked to reload the page.  
- State-changing requests, including login, whose `Origin` (or, if absent, `Referer`) header names a different site shall be rejected.

**FR53 — Login Throttling**  
- **Per username:** after **5** failed login attempts for the same username within **15 minutes** (counting only failures since the last successful login), further attempts for that username shall be refused until 15 minutes have passed since the oldest of those 5 failures.  
- **Per client address:** after **30** failed login attempts from the same client address within **15 minutes**, further attempts from that address shall be refused in the same way.  
- While refused, even a correct password shall not log the user in, and refused attempts shall not extend the waiting time.  
- The refusal message shall say how many minutes to wait, and shall be the same whether or not the username exists.

**FR54 — Accounts and Passwords**  
- Accounts shall be created, and passwords set, with a server-side account command run by an operator. It shall not be possible to do this from the web interface (FR3).  
- A password shall be 8–128 characters long, contain at least one letter and one digit, and differ from the username.  
- Setting a new password shall end all existing sessions of that account.  
- The login page shall not display any usernames or passwords.  
- Demo accounts with publicly known passwords may be created on first start-up only when demo data is enabled. Demo data shall be disabled in production. While any account still has its demo password, the server shall log a warning at start-up.

**FR55 — Security Headers**  
Every response shall include headers that:  
- restrict scripts, styles, images, fonts and connections to the site's own origin, and forbid plug-ins and inline scripts (Content Security Policy);  
- forbid the site from being embedded in frames on other sites;  
- stop browsers from guessing content types;  
- send the referring address only to the site itself.  
When the site is served over HTTPS, responses shall also tell browsers to use HTTPS for future visits (HSTS). Interactive API documentation pages, if enabled, may be exempt from the Content Security Policy.

**FR56 — HTTPS**  
In production the site shall be served only over HTTPS (for example behind a TLS-terminating reverse proxy), and the server shall be configured accordingly so that cookies are marked Secure (FR51) and HSTS is sent (FR55).

**FR57 — Request Size Limit**  
Requests whose body is larger than **6 MB** shall be rejected before they are processed, with a message that the request is too large. (The largest legitimate request is a product with a 5 MB image, FR14.)

**FR58 — Error Responses**  
Unexpected server errors shall produce a generic message without technical details (no stack traces, file paths or database messages). The details shall be written to the server log.

**FR59 — Security Logging**  
The server shall log security events — successful logins, failed logins, refused (throttled) logins, logouts, password changes and rejected anti-forgery checks — with the time, the username (if any) and the client address. Passwords, session identifiers and anti-forgery tokens shall never be logged.

## 10. Product Catalogue

**FR60 — Categories**  
Administrators shall be able to create, rename and delete product categories on the Product Management page.  
- A category name is 1–50 characters after removing leading and trailing spaces, and must be unique, ignoring letter case.  
- A product belongs to at most one category. A product without a category is shown as "Uncategorised".  
- Each category shows the number of products in it. Deleting a category requires confirmation; its products remain and become uncategorised.  
- Customers see the list of categories that contain at least one product.

**FR61 — Product Description**  
A product may have a plain-text description of up to 2,000 characters. Line breaks shall be kept when it is displayed; any markup in it shall be shown as text, not interpreted.

**FR62 — Multiple Product Images**  
A product has **1 to 8** images. The first image is the **main image**, used in product lists, the cart, checkout and orders.  
- In the product form, administrators can add images (several can be selected at once), remove images, and change their order, including choosing which image is the main image.  
- At least one image must remain; the form shall not allow saving a product without images.

**FR63 — Pagination**  
Long product lists are split into pages (FR7, FR15).  
- The page shall show which products are displayed and the total number (e.g. "Showing 13–24 of 40 products"), and controls to go to the previous, next, first and last page, and to nearby page numbers.  
- Changing the search, filters or sort order returns to the first page.  
- A page number beyond the last page shows the last page; a missing or invalid page number shows the first page.

**FR64 — Sorting**  
Customers can sort the product list by: **Newest** (default), **Price: low to high**, **Price: high to low**, and **Name: A to Z**. Administrators can additionally sort by **Stock: low to high** (total stock over all sizes). Products that are equal under the chosen order are listed newest first.

**FR65 — Filtering**  
- Customers can filter the product list by **category**, by **price range** (minimum and/or maximum price), by **size** (only products that have that size in stock), and to **in-stock products only** (products with at least one size in stock).  
- Administrators can filter the product list by category.  
- Filters, search and sorting can be combined; a product must meet all chosen conditions.  
- The price range accepts non-negative amounts with at most two decimal places; if the minimum is greater than the maximum, the system shall show a message and not apply the range.  
- The active filters shall be visible and can be cleared individually or all at once.

**FR66 — Shareable List State**  
The current search, filters, sort order and page shall be reflected in the page address, so that reloading the page, using the browser's back and forward buttons, or opening a copied link shows the same list.

**FR67 — Catalogue Performance**  
Searching, filtering, sorting and counting shall be done by the database, and only the products of the requested page shall be loaded and sent to the browser. The server shall not load the whole catalogue to answer a list request.

## 11. Deployment, Data and Quality

**FR68 — Supported Databases**  
The system shall run on **PostgreSQL** (version 14 or later) in production. **SQLite** may be used for local development and automated tests. All functions in this document shall behave the same on both; where the databases differ (for example in letter-case folding of non-English text), the difference shall be documented.

**FR69 — Schema Migrations**  
- Every change to the database structure shall be delivered as a numbered migration script kept with the code. A single command shall bring any database — empty or created by an earlier version — to the current structure without losing data.  
- Databases created before migrations were introduced (rev. 5 and earlier) shall be recognised and brought under migration control automatically.  
- The server shall refuse to start if the database structure is older than the code expects, with a message naming the command to run. For local development, the server may apply migrations automatically at start-up; this can be turned off.  
- Migrations shall be safe to start from several server processes at once: only one shall apply them.

**FR70 — Configuration**  
All settings that differ between environments — database connection, upload folder, demo data, HTTPS mode, session lifetime, automatic migrations — shall be read from environment variables, with defaults suitable for local development. Passwords and other secrets shall not be stored in the repository; example configuration files shall contain only placeholders.

**FR71 — Container Deployment**  
- The project shall provide a container image definition and a configuration that starts the application together with a PostgreSQL database using one command.  
- The application container shall run as a non-root user, apply pending migrations before it starts serving, and keep the database and uploaded images in persistent storage that survives replacing the containers.  
- Demo data shall be off and HTTPS mode on by default in the container configuration (FR54, FR56); an override for local trials may enable demo data.

**FR72 — Health Check**  
The system shall provide an unauthenticated health endpoint that reports whether the application can reach its database, answering success when it can and a "service unavailable" error when it cannot. It shall not reveal any other information. The container configuration shall use it to detect an unhealthy application.

**FR73 — Backups**  
The documentation shall describe how to back up and restore the database and the uploaded images, and how to check that a backup can be restored.

**FR74 — Automated Tests**  
- Automated tests shall cover the functional requirements of this document. They shall be run against both SQLite and PostgreSQL (FR68).  
- End-to-end tests shall drive the real application in a web browser through the main flows: logging in for both roles, browsing with search, filters and pagination, cart, checkout, placing and cancelling an order, product, category and order management, and the security headers and content security policy (FR55). They shall start their own application instance with its own data and run with one command.

**FR75 — Code Checks**  
Python code shall pass an automatic static check (unused or undefined names, imports, common bug patterns), and all JavaScript files shall pass a syntax check.

**FR76 — Continuous Integration**  
On every push and pull request, an automated pipeline shall run the code checks (FR75), the automated tests on both databases and in a browser (FR74), and build the container image and verify that it starts and reports healthy (FR71, FR72). A change shall be merged only when the pipeline succeeds.

**FR77 — Reproducible Builds**  
Application dependencies shall be pinned to exact versions, and the container image shall be built from a pinned base image using only the repository and published package sources, so that the same commit produces an equivalent image.

## 12. Payments

**FR78 — Payment Flow**  
- After placing an order (FR41), the customer is sent to a payment page hosted by the payment provider, showing the shop's name, the order number and the amount payable.  
- The provider tells the shop the result in a signed notification sent directly from server to server (FR81). Only this notification can mark an order **Paid**; the customer returning to the shop's pages, or anything the browser sends, cannot.  
- When the customer returns from the provider, the order page shows the result. If the notification has not arrived yet, the page shall say that the payment is being confirmed and update itself when it arrives.  
- The shop shall never receive or store card details; they are entered only on the provider's page.

**FR79 — Payment Deadline**  
- An order awaiting payment has a payment deadline, **30 minutes** after it was placed by default (configurable, FR70).  
- When the deadline has passed and the order is still awaiting payment, the system shall cancel it and return its items to stock within one minute, recording the system as the actor in the status history (FR47).  
- The customer cannot start a payment after the deadline; the payment page offered by the provider shall expire at the same time.  
- A payment confirmed while the order is still awaiting payment is accepted even if it arrives slightly after the deadline. A payment confirmed after the order has been cancelled shall be refunded automatically (FR82).

**FR80 — Payment Attempts**  
- If a payment fails or the customer leaves the provider's page without paying, the order stays awaiting payment, and the customer can try again with **Pay now** on the order page until the deadline.  
- An unfinished payment page is reused when the customer tries again; a failed or abandoned one is replaced by a new attempt.  
- An order can be paid only once. If a second payment for the same order is confirmed (for example, from another browser tab), it shall be refunded automatically.

**FR81 — Payment Notifications**  
- The shop shall accept payment notifications only when their signature is valid for the provider's secret key and their timestamp is no more than **5 minutes** old. Other notifications shall be rejected and logged as security events (FR59).  
- Each notification shall be processed at most once, even if the provider sends it again or two copies arrive at the same time.  
- The amount and currency in a payment confirmation must match the payment; otherwise the payment is treated as failed and the mismatch is logged.  
- Notifications for unknown payments shall be acknowledged and logged but have no other effect.

**FR82 — Refunds**  
- Cancelling a paid order, and the cases in FR79 and FR80, shall start a refund of the full amount paid. The refund is recorded with status **Pending**, then **Refunded** or **Failed** depending on the provider's answer.  
- A failed refund shall be shown to administrators on the order, with a **Retry refund** action. Customers see the refund status on their order.  
- A payment shall never be refunded more than once.

**FR83 — Payment Records**  
For each order, the system shall keep every payment attempt (provider, provider reference, amount, status, reason for failure, time started, time paid) and every refund (amount, status, provider reference, reason for failure, times). Customers see the payments and refunds of their own orders; administrators see those of all orders.

**FR84 — Mock Payment Provider**  
- Until a real payment provider is connected, the system shall use a built-in **mock payment provider** that behaves like a real one — its own hosted payment page, deadline, signed notifications and refunds — but moves no money.  
- Its payment page shall state clearly that it is a test payment and that no real money is charged, and shall let the user choose the outcome: **pay successfully**, **simulate a declined payment**, or **cancel and return to the shop**.  
- The server shall log a warning at start-up while the mock provider is in use. It must be replaced by a real provider before the shop takes real orders.

**FR85 — Payment Provider Interface**  
Payment providers shall be connected through one interface — start a payment and get the provider's page address, check whether a started payment can still be used, verify and read a notification, and refund a payment — so that a real provider can be added without changing the order logic. The provider in use shall be chosen by configuration (FR70).

**FR86 — Payment Status Display**  
- An order awaiting payment shall show the time left to pay, counting down, and a **Pay now** button.  
- The order detail pages shall show the payment status, the latest payment attempt and any refunds (FR83).  
- The payment-related settings (provider, deadline, notification secret, currency) shall be configurable through environment variables (FR70).

**FR87 — Orders from Earlier Versions**  
Orders placed before payments were introduced (status **Placed**) shall be treated as **Paid**: they can be shipped, completed or cancelled as paid orders, but cancelling them starts no refund, because nothing was paid through the system.
