# Online Shopping Website — Functional Requirements

## 1. Login and Access Control

**FR1 — Role Selection**  
The system shall provide a login page where visitors can select either **Administrator Login** or **Customer Login**.

**FR2 — User Authentication**  
The system shall authenticate administrators and customers using their assigned account credentials. The system shall display an error message when the supplied credentials are invalid.

**FR3 — Preconfigured Customer Accounts**  
The system shall support preconfigured customer accounts for this version. Customer self-registration shall not be provided.

**FR4 — Role-Based Redirection**  
After successful authentication, the system shall redirect administrators to the Product Management page and customers to the Product Browsing page.

**FR5 — Role-Based Access Control**  
The system shall restrict product management functions to authenticated administrators and shopping functions to authenticated customers.

**FR6 — Logout**  
The system shall allow authenticated users to log out and return to the login page.

## 2. Administrator — Product Management

**FR7 — View Product List**  
The system shall allow administrators to view a list of existing products, including each product's image, name, price, and stock quantity for each available size.

**FR8 — Add Product**  
The system shall allow administrators to add a product by providing its image, name, price, and stock quantities for one or more sizes selected from **S, M, L, and XL**.

**FR9 — View Product Details**  
The system shall allow administrators to view the complete information of an existing product, including its image, name, price, available sizes, and size-specific stock quantities.

**FR10 — Update Product**  
The system shall allow administrators to update an existing product's image, name, price, available sizes, and stock quantities for each size.

**FR11 — Delete Product**  
The system shall allow administrators to delete an existing product after confirming the deletion.

**FR12 — Search Products in Management**  
The system shall allow administrators to search for products by keyword in the Product Management page.

**FR13 — Validate Product Information**  
The system shall validate product information before saving. The product name and image shall be required, the price shall be greater than zero, each size-specific stock quantity shall be a non-negative integer, and sizes shall be limited to **S, M, L, and XL**. At least one size shall be available for a product.

**FR14 — Handle Product Images**  
The system shall allow administrators to upload or replace a product image and shall display an error message if the image cannot be uploaded or does not meet the supported image format requirements.

## 3. Customer — Product Browsing and Search

**FR15 — Browse Products**  
The system shall display a list of products to customers, showing each product's image, name, and price.

**FR16 — Search Products**  
The system shall allow customers to search for products using keywords matched against product names. The search shall be case-insensitive, and the system shall display matching results or a message when no products match.

**FR17 — View Product Details**  
The system shall allow customers to select a product and open its detail page. The page shall display the product image, name, price, available sizes, and stock quantity for each size.

**FR18 — Select Product Size**  
The system shall allow customers to select one available size from **S, M, L, and XL** before adding a product to the cart or purchasing it directly. Sizes with no stock shall not be selectable for purchase.

## 4. Customer — Shopping Cart

**FR19 — Add to Cart**  
The system shall allow customers to add a product with a selected size and quantity to their shopping cart, provided sufficient stock is available. The requested quantity shall be a positive integer.

**FR20 — Handle Duplicate Cart Items**  
When a customer adds the same product in the same size more than once, the system shall combine the items into one cart entry and update its quantity.

**FR21 — View Shopping Cart**  
The system shall allow customers to view their cart items, including each product's image, name, selected size, quantity, unit price, and subtotal, as well as the total cart price.

**FR22 — Update Cart Quantity**  
The system shall allow customers to change the quantity of a cart item. The new quantity shall be a positive integer and shall not exceed the available stock for the selected size.

**FR23 — Remove Cart Items**  
The system shall allow customers to remove individual items from their shopping cart.

**FR24 — Handle Empty Cart**  
The system shall display an appropriate message and shall not allow customers to proceed to checkout when the shopping cart is empty.

**FR25 — Recalculate Cart Prices**  
The system shall calculate each cart item's subtotal as the current unit price multiplied by its quantity, and calculate the cart total as the sum of all item subtotals. The system shall use the current product price when displaying the cart and checkout summary.

**FR26 — Proceed to Checkout from Cart**  
The system shall allow customers to proceed from a non-empty shopping cart to the Checkout page with all cart items and their selected sizes and quantities.

## 5. Customer — Direct Purchase and Checkout

**FR27 — Buy Now**  
The system shall allow customers to select a size and quantity on a product detail page and proceed directly to the Checkout page without adding the product to the shopping cart.

**FR28 — Display Checkout Summary**  
The system shall display all items selected for checkout, including product names, images, sizes, quantities, unit prices, subtotals, and the total amount payable. The same summary format shall be used for cart checkout and direct purchase.

**FR29 — Validate Stock at Checkout**  
The system shall revalidate the requested quantity against the current stock for each selected size before allowing the customer to continue. If stock is insufficient or a product is no longer available, the system shall notify the customer and identify the affected item.

**FR30 — Handle Price Changes**  
If a product's price changes after it has been added to the cart, the system shall use the current price in the cart and checkout summary and recalculate the relevant subtotals and total.

**FR31 — Return from Checkout**  
The system shall allow customers to return from the Checkout page to the shopping cart or product detail page to revise their selections.

**FR32 — Payment Page and Scope Limitation**  
The system shall provide a checkout/payment page for both cart checkout and direct purchase, displaying the order summary and total amount. Actual payment methods, payment processing, payment confirmation, and order fulfilment shall not be implemented in this version.

## 6. Availability and Error Handling

**FR33 — Handle Out-of-Stock Products**  
The system shall prevent customers from purchasing a size whose stock quantity is zero. The system may continue to display the product, but it shall clearly indicate that the size is out of stock.

**FR34 — Handle Deleted or Unavailable Products**  
If a product in a customer's cart becomes unavailable or is deleted before checkout, the system shall notify the customer and prevent that item from being checked out.

**FR35 — Provide Feedback for Invalid Actions**  
The system shall display a clear message when an operation cannot be completed, including invalid product information, unavailable stock, failed image upload, invalid login credentials, or an unsuccessful product search.
