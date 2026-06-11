> ## Documentation Index
> Fetch the complete documentation index at: https://sendcloud.dev/llms.txt
> Use this file to discover all available pages before exploring further.

# Create a parcel

<Warning>
  This page applies to v2 of the Sendcloud API and is no longer maintained. To learn more about switching to API v3,
  read our [migration guide](/docs/getting-started/migration-guidelines-for-api-v3#parcels/shipments).
</Warning>

Sendcloud's flexible shipping API covers every part of the shipping process, from label creation right up to the point of delivery. Ready to put your shipping processes on autopilot? Read on to learn how to create your first parcel with Sendcloud's **Shipping API**.

There are two ways to create a parcel via the API:

**Method 1: Create a parcel object**

* This is the most flexible means of creating a parcel. The parcel object is created in the Sendcloud system, but the parcel is not immediately announced with the carrier.
* This gives you time to continue making changes to the parcel data and decide on a shipping method right up until the moment you're ready to create the label.
* Parcels can be processed either via the [Sendcloud platform](https://support.sendcloud.com/hc/en-us/articles/360025263691-Process-your-orders-), or you can perform all interactions via the API, depending on your specific use case.

**Method 2: (Advanced option): Create the parcel and shipping label in a single API call**

* This method is described in more detail at the end of this tutorial.

To help get you started, this guide will cover the basics of **creating a parcel via the API**, step-by-step.

Once the parcel is created, you can continue on to the next steps to learn how to choose a shipping method and print the label.

## Before you begin

1. Make sure you've completed basic account set up. See [Quickstart](/docs/getting-started)
2. You'll need to have obtained your API keys so you can authenticate with our API. See [Authentication](/docs/getting-started/authentication)
3. You'll need access to a tool that allows you to make API calls. Examples are [Postman](https://www.postman.com/sendcloud-api) and [Insomnia](https://insomnia.rest/download).

### The Create a parcel or parcels API endpoint

Parcels are created by sending a HTTP `POST` request to the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint.

```http Request method and URL theme={null}
POST https://panel.sendcloud.sc/api/v2/parcels
```

#### Authorization header

Every time you make an API call, you need to [authenticate](/docs/getting-started/authentication) your connection to Sendcloud by including your API keys through a HTTP header.

```http Authorization header theme={null}
Authorization: Basic <credentials>
```

## Step 1: Prepare your request

In the body of your HTTP request, you need to specify all the required information for the shipping label. Below you can find an example which will create a parcel object in your Sendcloud account.

```json Example request body theme={null}
{
  "parcel": {
    "name": "John Doe",
    "company_name": "FlowerShop",
    "email": "john@doe.com",
    "telephone": "+31611223344",
    "address": "Fürstenrieder Str.",
    "house_number": "70",
    "address_2": "",
    "city": "Munich",
    "country": "DE",
    "postal_code": "80686",
    "country_state": null,
    "to_service_point": 10168633,
    "to_post_number": 262373726,
    "customs_invoice_nr": "",
    "customs_shipment_type": null,
    "parcel_items": [
      {
        "description": "T-Shirt",
        "hs_code": "6109",
        "origin_country": "SE",
        "product_id": "898678671",
        "properties": {
          "color": "Blue",
          "size": "Medium"
        },
        "quantity": 2,
        "sku": "TST-OD2019-B620",
        "value": "19.95",
        "weight": "0.9"
      },
      {
        "description": "Laptop",
        "hs_code": "84713010",
        "origin_country": "DE",
        "product_id": "5756464758",
        "properties": {
          "color": "Black",
          "internal_storage": "2TB"
        },
        "quantity": 1,
        "sku": "LT-PN2020-B23",
        "value": "876.97",
        "weight": "1.69"
      }
    ],
    "weight": "3.49",
    "length": "31.5",
    "width": "27.2",
    "height": "12.7",
    "total_order_value": "896.92",
    "total_order_value_currency": "EUR",
    "shipment": {
      "id": 1316,
      "name": "DHL Parcel Connect 2-5kg to ParcelShop"
    },
    "shipping_method_checkout_name": "Battery WarehouseX DHL",
    "sender_address": 1,
    "quantity": 1,
    "total_insured_value": 0,
    "is_return": false,
    "request_label": false,
    "apply_shipping_rules": false,
    "request_label_async": false
  }
}
```

<Note>
  The important thing to note here is that the `request_label` parameter is set to `false`. This allows you to create a
  parcel without announcing it to a carrier or creating a shipping label.
</Note>

The parcel will be created using the **default** shipping method you saved in your account, and can be updated later.

Also note that specific carriers might impose [additional requirements on address-related fields](/docs/shipping/address-field-limits/).

### Other request fields

There are many other additional fields that you can specify when creating a parcel. An example would be the `sender_address` parameter which lets you ship a parcel from a different sender location, or the parameters related to customs information for international shipping.

You can find a list of the supported fields in our [API reference](/api/v2/parcels/create-a-parcel-or-parcels/).

## Step 2: Send your request

Take the example above, and use it to make a `POST` request to `http://panel.sendcloud.sc/api/v2/parcels`.

```http Request method, URL, and Authorization header theme={null}
POST https://panel.sendcloud.sc/api/v2/parcels
Authorization: Basic <base64-encoded-token>
```

If everything went well, you'll receive a HTTP 200 [status code](https://en.wikipedia.org/wiki/List_of_HTTP_status_codes) and a `parcel` object in the response body.

See an example of the response body in the [API reference](/api/v2/parcels/create-a-parcel-or-parcels).

#### Some things to note about the response

* The newly-created parcel will be assigned a parcel `id`, e.g. `"id": 189169249`. This is the unique parcel identifier which we will use whenever we want to update a parcel or create the label via the API.
* The current status of the newly-created parcel will be `"No label"`. It will appear in the Sendcloud platform under the **Incoming order view** with the message **Ready to process** until we create a label for it.
  <img src="https://mintcdn.com/sendcloud/1qLmoV2zg9wO4FD0/images/docs/shipping/create-a-label-guide.jpg?fit=max&auto=format&n=1qLmoV2zg9wO4FD0&q=85&s=db8b2601bb59b45d32d2e495f34e22cd" alt="Screenshot of the Incoming order view, showing the newly-created parcel with the status &#x22;Ready to process&#x22;" width="1918" height="610" data-path="images/docs/shipping/create-a-label-guide.jpg" />

## Step 3: Create the shipping label

To create shipping labels via the API, you need to use the [Update a parcel endpoint](/api/v2/parcels/update-a-parcel) to update the value of `request_label` to `true`.

Via this endpoint, you can also make changes to any of the properties that can be used for creating a parcel.

### Generating a label for an existing parcel

In this example, we will update parcel `"id": 1` as follows:

* Create the shipping label by providing the data `"request_label": true`
* Change the `name` of the recipient to a new value
* Change the shipping method by providing the corresponding `id`. In this example, we'll be using the method **"Unstamped letter"** to create a test label.

<Tip>
  You'll be invoiced for any shipping labels you create if you don't cancel or delete them within the [cancellation
  deadline](https://support.sendcloud.com/hc/en-us/articles/360025143991-How-do-I-cancel-my-shipment). You can create
  [test labels](/docs/getting-started/test-labels/) without receiving a charge by using the shipping method Unstamped
  letter (`"id": 8`)
</Tip>

```http Request method, URL, and Authorization header theme={null}
PUT https://panel.sendcloud.sc/api/v2/parcels
Authorization: Basic <base64-encoded-token>
```

```json Example request body theme={null}
{
  "parcel": {
    "id": 1,
    "request_label": true,
    "name": "Mr Test",
    "shipment": {
      "id": 8,
      "name": "Unstamped letter"
    }
  }
}
```

Once you've prepared the response body, make a `PUT` request to the [Update a parcel endpoint](/api/v2/parcels/update-a-parcel). Make sure to include your authentication and content headers, as you did in Step 2.

If everything goes well, you should receive a response similar to the one below:

```json Example response body theme={null}
{
  "parcel": {
    "id": 1,
    "name": "Mr Test",
    "shipment": {
      "id": 8,
      "name": "Unstamped letter"
    },
    "status": {
      "id": 1000,
      "message": "Ready to send"
    },
    "label": {
      "normal_printer": [
        "https://panel.sendcloud.sc/api/v2/labels/normal_printer/1?start_from=0",
        "https://panel.sendcloud.sc/api/v2/labels/normal_printer/1?start_from=1",
        "https://panel.sendcloud.sc/api/v2/labels/normal_printer/1?start_from=2",
        "https://panel.sendcloud.sc/api/v2/labels/normal_printer/1?start_from=3"
      ],
      "label_printer": "https://panel.sendcloud.sc/api/v2/labels/label_printer/1"
    },
    "shipping_method": 8
    // ... other parcel data
  }
}
```

Notice that the response reflects the updates you have made to the customer `name`, and that the parcel `status` is now **"Ready to send"**. The shipping method has been updated to **"Unstamped letter"**.

## Step 4: Download the shipping label

At the end of the previous step, you should have received a response which contains some URLs under the `label` field. These URLs are your links to download the shipping label. Labels can be downloaded in PDF format and are provided in A4 size for normal printers, and A6 size for label printers.

Under `normal_printer`, the `start_from` value indicates the position of the label on an A4 size page:

* `0` = Top left
* `1` = Top right
* `2` = Bottom left
* `3` = Bottom right

You'll need to provide your API credentials again to access the link to download your labels. You can do this by making a `GET` request to the URL of the label you want to access, and including the `Authorization` header.

```http Request method, URL, and Authorization header theme={null}
GET https://panel.sendcloud.sc/api/v2/labels/normal_printer/1?start_from=0
Authorization: Basic <base64-encoded-token>
```

<Tip>
  Labels can also be downloaded in bulk directly from the Sendcloud platform under the **Created labels** tab, or via
  the [Retrieve multiple PDF labels](/api/v2/labels/retrieve-multiple-pdf-labels) and [Bulk PDF label
  printing](/api/v2/labels/bulk-pdf-label-printing) endpoints.
</Tip>

**Congrats!** You've just created your first parcel and downloaded the shipping label via the API.

## Next steps

You can continue reading more tutorials or dive directly into exploring our API references.

* [Choose a shipping method](/docs/shipping/shipping-methods) - learn how to retrieve the full list of shipping services available to you via Sendcloud
* [Tracking parcels](/docs/archive/tracking/tracking-parcels) - to see how you can track the delivery journey of your newly created parcel as it travels to your customer
* [Create a return](/docs/returns/return-portal) - read how you can create a return parcel shipment using the Sendcloud Returns API
* [API v2 reference](/api/v2/) and [API v3 reference](/api/v3/) - browse our API references to explore more options for creating parcels and managing your shipping processes.

## Advanced options

### Create a parcel and immediately request a label in a single API call

If you already know which shipping method you want to use to send your parcel, you can bypass Step 3 above by making a `POST` request to the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint, including `"request_label": "true"`.

<Note>
  When directly announcing parcels in this way, the `shipment` field is mandatory, and a shipping method `id` and `name`
  must be provided in the API request. If you're [shipping parcels
  internationally](/docs/shipping/international-shipping/), pay attention to the additional fields which become
  mandatory for customs documentations purposes. A full list of required parameters can be found in the [API
  reference](/api/v2/parcels/create-a-parcel-or-parcels).
</Note>

### Create a return parcel

You can use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint to create return labels via the API. The process for creating a return label via this method is the same as for creating a parcel, but you must set the value of the `is_return` property to `true` and specify the customer's address address in the `from_*` fields.

It's important to note that standard shipping methods don't apply to return parcels. You can find an overview of available return methods via the [List of all shipping methods](/api/v2/shipping-methods/retrieve-a-list-of-shipping-methods) endpoint and include the parameter `"is_return": true`.

<Info>
  You can also create returns using the **Returns API** by following the [Create a return
  guide](/docs/returns/return-portal/).
</Info>

### Ship parcels and retrieve methods for your sender addresses based in other countries

You can set up multiple sender addresses in your Sendcloud account, and specify which sender address you want to ship from when you create a parcel. See our [sender addresses documentation](/docs/getting-started/sender-addresses) for more info.

### Automatically apply your preferred shipping methods via shipping rules

Shipping rules are a Sendcloud feature which can be used in conjunction with the API to take the legwork out of manually choosing and selecting the best method for your created parcels. See our [shipping rules documentation](/docs/shipping/shipping-rules/) for more details.

### Print your brand logo on your shipping labels

You can customize a brand in your Sendcloud account to make use of handy marketing tools, such as customizable tracking notifications and branded return portals for each of your integrations. See more about creating your brand in our [help center](https://support.sendcloud.com/hc/en-us/articles/360041212392-How-to-set-up-your-brand-).

### Receive real time parcel status updates via Webhooks

There are two ways to receive real-time parcel event notifications:

* **Classic webhooks** — configure webhook URLs directly in the [Sendcloud platform](https://app.sendcloud.com/v2/settings/integrations/manage) or via the [Webhooks API](/api/v3/webhooks/index). This is the established approach for receiving parcel status updates.
* **Event Subscriptions API** — programmatically create [connections and subscriptions](/api/v3/event-subscriptions/index) to control where events are delivered and which events you listen for. Supports webhook endpoints and third-party integrations like Klaviyo.

<Note>The Event Subscriptions API is currently in **BETA**.</Note>



> ## Documentation Index
> Fetch the complete documentation index at: https://sendcloud.dev/llms.txt
> Use this file to discover all available pages before exploring further.

# Migration guidelines for API v3

## Why should you migrate to API v3?

API v3 delivers powerful new capabilities unavailable in v2 to streamline operations, which is especially relevant if you are shipping high volumes or handling complex shipments.

A standout improvement is **per-parcel customisation for multicollo shipments**, allowing you to specify individual weights, dimensions, items, and insurance amounts for each parcel. This removes the API v2 limitation where all parcels in a shipment had to share identical attributes, thereby enhancing accuracy and flexibility.

For single-collo shipments, **synchronous announcements now return labels instantly** within the API response, minimising the risk of rate limiting by combining shipment creation and label retrieval into a single call. This significantly reduces delays caused by multiple API requests to fetch labels.

Brand ID is now **decoupled from the sender address**, enabling more flexible and precise branding management.

API v3 allows your **entire workflow**, from creating orders to printing labels, to be handled programmatically via the API, eliminating the need for manual work in the Sendcloud platform and boosting automation efficiency.

### Exclusive API v3 Features

* **Label notes** (`parcel.label_notes`): Print SKUs for pick-and-pack efficiency, customer delivery instructions (e.g., "Ring the blue doorbell"), or personalised thank-yous.
* **SSCC tracking** (`parcel.sscc`): Monitor pallets or containers across the full supply chain.
* **Native ZPL labels** (`label_detail.mime_type`): Direct carrier ZPL output prevents scanning errors common with converted formats.
* **Delivery scheduling** (`delivery_dates.handover_at` / `deliver_at`): Notify carriers of planned handover times (ideal for warehouse pickups) and expected delivery to customers.
* **Validate a return**: Check that return shipment details are correct before label creation.
* **Manage shop order statuses and custom status mappings** for Prestashop v2 integrations.
* **Create, update and delete carrier contracts** via the API.
* **More pickup carriers** supported for scheduling pickups programmatically.
* **Create an external parcel for tracking**.

## What's changed?

### Managing orders

In API v3 we've introduced a dedicated Orders API to simplify order management. In API v2 these functionalities were spread across the Integrations and Parcels APIs, and some functionalities were only available for certified Sendcloud partners.

| Action                                                                      | API v2                                                                                                                                                                                                                                                                                                                                                | API v3                                                                                                           |
| --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Create an order that shows in the Sendcloud platform's Incoming orders page | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, passing `request_label: false` in the request body<br />OR<br />use the [Create or update a list of shipments](/api/v2/integrations/create-a-list-of-shipments) endpoint<sup>\*</sup> in the Integrations API                           | Use the [Create/update orders in batch](/api/v3/orders/create-update-orders-in-batch) endpoint in the Orders API |
| Get a list of incoming orders                                               | Use the [Retrieve a list of shipments](/api/v2/integrations/retrieve-a-list-of-shipments) endpoint in the Integrations API                                                                                                                                                                                                                            | Use the [Retrieve a list of orders](/api/v3/orders/retrieve-a-list-of-orders) endpoint in the Orders API         |
| Get a specific order                                                        | Use the [Retrieve a list of shipments](/api/v2/integrations/retrieve-a-list-of-shipments) endpoint in the Integrations API to fetch all shipments and then filter the results yourself (e.g. by `external_order_id`, `external_reference`, or `order_number`)                                                                                         | Use the [Retrieve an order](/api/v3/orders/retrieve-an-order) endpoint in the Orders API                         |
| Update an order                                                             | Update an **unannounced** parcel using the [Update a parcel](/api/v2/parcels/update-a-parcel) endpoint in the Parcels API<br />OR<br />Update the integration shipment by re-sending it (re-creating) using the [Create or update a list of shipments](/api/v2/integrations/create-a-list-of-shipments) endpoint<sup>\*</sup> in the Integrations API | Use the [Update an order](/api/v3/orders/update-an-order) endpoint in the Orders API                             |
| Delete or cancel an order                                                   | Use the [Delete a shipment](/api/v2/integrations/delete-a-shipment) endpoint in the Integrations API                                                                                                                                                                                                                                                  | Use the [Delete an order](/api/v3/orders/delete-an-order) endpoint in the Orders API                             |

<sup>\*</sup> This endpoint is only available for certified Sendcloud partners.

### Shipping an existing order (creating labels)

The new Ship an Order API in v3 allows you to create a parcel and request a label for an existing order in Sendcloud in one step, both asynchronously and synchronously. In API v2, you could only do this asynchronously.

| Action                                                               | API v2                                                                                                                                                           | API v3                                                                                                                                                                         |
| -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Create a shipment and request the label immediately (asynchronously) | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, passing `request_label: false` in the request body | Use the [Request a label for one or more orders asynchronously](/api/v3/ship-an-order/request-a-label-for-one-or-more-orders-asynchronously) endpoint in the Ship an Order API |
| Create a shipment and request the label immediately (synchronously)  | 🚫 Not supported                                                                                                                                                 | Use the [Request a label for a single order synchronously](/api/v3/ship-an-order/request-a-label-for-a-single-order-synchronously) endpoint in the Ship an Order API           |

#### Shipments API v3 vs Ship an Order API v3

The Ship an Order API is specifically designed to create shipments and request labels for **existing orders** in Sendcloud, in a single step.

In contrast, the Shipments API allows you to create a shipment and request a label in a single step **without** having an existing order in Sendcloud.

Note that the Shipments API supports the following features which are not currently available in the Ship an Order API:

* synchronous multicollo
* importing order notes
* order split
* shipping rules controls
* label creation when the order doesn't exist in Sendcloud
* sender address support (dynamic)
* instructions on handling failures stemming from carrier validation errors

### Integrations

New in the Integrations API v3, we've added the ability to manage shop order statuses and custom status mappings for Prestashop v2 integrations.

Custom status mappings allow you to define how your shop order statuses correspond to Sendcloud's internal status categories, enabling more accurate order processing.

| Action                                                                                 | API v2                                                                                                                                                                                                                                                                                                                                                                                                          | API v3                                                                                                                                                                                    |
| -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| List all your integrations (i.e. connected shops/systems)                              | Use the [Retrieve a list of integrations](/api/v2/integrations/retrieve-a-list-of-integrations) endpoint in the Integrations API (v2)                                                                                                                                                                                                                                                                           | Use the [Retrieve a list of integrations](/api/v3/integrations/retrieve-a-list-of-integrations) endpoint in the Integrations API (v3)                                                     |
| Get the settings for one specific integration                                          | Use the [Retrieve an integration](/api/v2/integrations/retrieve-an-integration) endpoint in the Integrations API (v2)                                                                                                                                                                                                                                                                                           | Use the [Retrieve an integration](/api/v3/integrations/retrieve-an-integration) endpoint in the Integrations API (v3)                                                                     |
| Update integration settings (full) → replace all settings                              | Use the [Update an integration](/api/v2/integrations/update-an-integration) endpoint in the Integrations API (v2)                                                                                                                                                                                                                                                                                               | 🚫 Not supported - use the endpoint below instead.                                                                                                                                        |
| Update integration settings (partial) → change some settings without touching the rest | Use the [Partially update an integration](/api/v2/integrations/partially-update-an-integration) endpoint in the Integrations API (v2)                                                                                                                                                                                                                                                                           | Use the [Update certain parts of an integration](/api/v3/integrations/update-certain-parts-of-an-integration) endpoint in the Integrations API (v3)                                       |
| Delete an integration                                                                  | Use the [Delete an integration](/api/v2/integrations/delete-an-integration) endpoint in the Integrations API (v2)                                                                                                                                                                                                                                                                                               | Use the [Delete an integration](/api/v3/integrations/delete-an-integration) endpoint in the Integrations API (v3)                                                                         |
| Retrieve or create integration exception logs                                          | Use these Integrations API (v2) endpoints: <ul><li>[Retrieve all integration exception logs](/api/v2/integrations/retrieve-all-integration-exception-logs)</li><li>[Retrieve exception logs for a specific integration](/api/v2/integrations/retrieve-exception-logs-for-a-specific-integration)</li><li>[Create integration exceptions logs](/api/v2/integrations/create-integration-exception-logs)</li></ul> | 🚫 Not supported                                                                                                                                                                          |
| Get shop order statuses (for the Prestashop v2 integration only)                       | 🚫 Not supported                                                                                                                                                                                                                                                                                                                                                                                                | Use the [Retrieve shop order statuses for an integration](/api/v3/integrations/retrieve-shop-order-statuses-for-an-integration) endpoint in the Integrations API (v3)                     |
| Create/overwrite shop order statuses (for the Prestashop v2 integration only)          | 🚫 Not supported                                                                                                                                                                                                                                                                                                                                                                                                | Use the [Create or overwrite shop order statuses](/api/v3/integrations/create-or-overwrite-shop-order-statuses) endpoint in the Integrations API (v3)                                     |
| Get custom status mapping (for the Prestashop v2 integration only)                     | 🚫 Not supported                                                                                                                                                                                                                                                                                                                                                                                                | Use the [Retrieve custom status mapping for an integration](/api/v3/integrations/retrieve-custom-status-mapping-for-an-integration) endpoint in the Integrations API (v3)                 |
| Create/update custom status mapping (for the Prestashop v2 integration only)           | 🚫 Not supported                                                                                                                                                                                                                                                                                                                                                                                                | Use the [Create or update custom status mapping for an integration](/api/v3/integrations/create-or-update-custom-status-mapping-for-an-integration) endpoint in the Integrations API (v3) |

### Parcels/Shipments

In API v2, the Parcels API was used to create shipments and request labels. In API v3, this has been replaced by the Shipments API.

You can also refer to the following field changes when migrating from the Parcels API v2 to the Shipments API v3:

* [Address fields](#address-fields)
* [Customs fields](#customs-fields)
* [Sender address fields](#sender-address-fields)
* [Shipment/Parcel fields](#shipment/parcel-fields)
* [Shipping methods vs. Shipping products vs. Shipping prices vs. Shipping options fields](#shipping-methods-vs-shipping-products-vs-shipping-prices-vs-shipping-options-fields)

| Action                                                                                                                                                                                                                                                                   | API v2                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | API v3                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Create a parcel **without** shipping rules or defaults (synchronously)                                                                                                                                                                                                   | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, passing `request_label_async: false` and `apply_shipping_rules: false` in the request body                                                                                                                                                                                                                                                                                                           | Use the [Create and announce a shipment synchronously](/api/v3/shipments/create-and-announce-a-shipment-synchronously) endpoint in the Shipments API                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Create a parcel **without** shipping rules or defaults (asynchronously)                                                                                                                                                                                                  | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, passing `request_label_async: true` and `apply_shipping_rules: false` in the request body                                                                                                                                                                                                                                                                                                            | Use the [Create and announce a shipment asynchronously](/api/v3/shipments/create-and-announce-a-shipment-asynchronously) endpoint in the Shipments API                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Create a parcel **with** shipping rules or defaults (synchronously)                                                                                                                                                                                                      | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, passing `request_label_async: false` and `apply_shipping_rules: true` in the request body                                                                                                                                                                                                                                                                                                            | Use the [Create a shipment with rules and/or defaults and announce it synchronously](/api/v3/shipments/create-a-shipment-with-rules-and-or-default-and-announce-it-synchronously) endpoint in the Shipments API                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| Create a parcel **with** shipping rules or defaults (asynchronously)                                                                                                                                                                                                     | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, passing `request_label_async: true` and `apply_shipping_rules: true` in the request body                                                                                                                                                                                                                                                                                                             | Use the [Create a shipment with rules and/or defaults and announce it asynchronously](/api/v3/shipments/create-a-shipment-with-rules-and-or-default-and-announce-it-asynchronously) endpoint in the Shipments API                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Create multiple parcels at once                                                                                                                                                                                                                                          | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, sending an array of parcels in the request body                                                                                                                                                                                                                                                                                                                                                      | 🚫 Not supported                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Create a multicollo shipment                                                                                                                                                                                                                                             | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, setting `quantity` to a number greater than 1                                                                                                                                                                                                                                                                                                                                                        | Use any [Shipments API](/api/v3/shipments) `POST` endpoint, by creating more than one parcel object in the parcels array                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Retrieve your label after announcement - PDF label                                                                                                                                                                                                                       | Use one of the following v2 endpoints: <ul><li>[Retrieve PDF labels for a label printer](/api/v2/labels/retrieve-pdf-labels-for-a-label-printer)</li><li>[Retrieve a specific PDF label for a label printer](api/v2/labels/retrieve-a-specific-pdf-label-for-a-label-printer)</li><li>[Retrieve parcel documents](/api/v2/parcel-documents/retrieve-parcel-documents) with the `type` path parameter set to `label` and the `Accept` header set to `application/pdf`</li></ul>                                     | Use one of these options:<ul><li>[Retrieve a parcel document](/api/v3/parcel-documents/retrieve-a-parcel-document), with the `type` path parameter set to `label` and the `Accept` header set to `application/pdf`</li><li>Use the response from [Create and announce a shipment synchronously](/api/v3/shipments/create-and-announce-a-shipment-synchronously) or [Create a shipment with rules and/or defaults and announce it synchronously](/api/v3/shipments/create-a-shipment-with-rules-and-or-default-and-announce-it-synchronously) (for **single-collo** shipments only)</li></ul>                                                                                                                              |
| Retrieve your label after announcement - ZPL/PNG label                                                                                                                                                                                                                   | [Retrieve parcel documents](/api/v2/parcel-documents/retrieve-parcel-documents) with the `type` path parameter set to `label` and the `Accept` header set to `application/png` or `application/zpl`                                                                                                                                                                                                                                                                                                                | Use one of these options:<ul><li>[Retrieve a parcel document](/api/v3/parcel-documents/retrieve-a-parcel-document), with the `type` path parameter set to `label` and the `Accept` header set to `application/png` or `application/zpl`</li><li>Use the response from [Create and announce a shipment synchronously](/api/v3/shipments/create-and-announce-a-shipment-synchronously) or [Create a shipment with rules and/or defaults and announce it synchronously](/api/v3/shipments/create-a-shipment-with-rules-and-or-default-and-announce-it-synchronously) (for **single-collo** shipments only)</li></ul>                                                                                                         |
| Understand if your shipment was successfully announced on the carrier side                                                                                                                                                                                               | Use one of these options: <ul><li>Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, passing `"errors": "carrier-verbose"` and `"request_label": true` in the request body. If there's a carrier error the API will respond with a `400` status code</li><li>Use the [Retrieve a parcel](/api/v2/parcels/retrieve-a-parcel) or [Retrieve parcels](/api/v2/parcels/retrieve-parcels) endpoints in the Parcels API, and check the errors object</li></ul> | Use one of these options: <ul><li>[Create and announce a shipment synchronously](/api/v3/shipments/create-and-announce-a-shipment-synchronously) or [Create a shipment with rules and/or defaults and announce it synchronously](/api/v3/shipments/create-a-shipment-with-rules-and-or-default-and-announce-it-synchronously) endpoints in the Shipments API, and check the errors object. Unlike API v2, if there's a carrier error the API still returns a `200` status code.</li><li>Use the [Retrieve a shipment](/api/v3/shipments/retrieve-a-shipment) or [Retrieve shipments](/api/v3/shipments/retrieve-shipments) endpoints in the Shipments API, and check the errors object</li></ul>                          |
| List your parcels                                                                                                                                                                                                                                                        | Use the [Retrieve parcels](/api/v2/parcels/retrieve-parcels) endpoint in the Parcels API                                                                                                                                                                                                                                                                                                                                                                                                                           | Use the [Retrieve shipments](/api/v3/shipments/retrieve-shipments) endpoint in the Shipments API                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Get a specific parcel                                                                                                                                                                                                                                                    | Use the [Retrieve a parcel](/api/v2/parcels/retrieve-a-parcel) endpoint in the Parcels API                                                                                                                                                                                                                                                                                                                                                                                                                         | Use the [Retrieve a shipment](/api/v3/shipments/retrieve-a-shipment) endpoint in the Shipments API                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Update your parcel                                                                                                                                                                                                                                                       | Use the [Update a parcel](/api/v2/parcels/update-a-parcel) endpoint in the Parcels API.<br /><br />Only supported for parcels previously announced with `request_label: false` **or** those that were created with a 200 code, but no label was returned (a carrier error was returned instead)                                                                                                                                                                                                                    | 🚫 Not supported.<br /><br />To fix carrier errors in API v3, a new parcel needs to be created.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| Cancel a parcel                                                                                                                                                                                                                                                          | Use the [Cancel a parcel](/api/v2/parcels/cancel-a-parcel) endpoint in the Parcels API                                                                                                                                                                                                                                                                                                                                                                                                                             | Use the [Cancel a shipment](/api/v3/shipments/cancel-a-shipment) endpoint in the Shipments API                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| Define what carrier service you'd like to use to ship your parcel                                                                                                                                                                                                        | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, passing the `shipment.id` field.<br /><br />To get the `shipment.id` value, you can use the [Shipping methods API](/api/v2/shipping-methods) or the [Shipping products API](/api/v2/shipping-products).                                                                                                                                                                                              | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and specify the `shipping_option_code` in the `ship_with.properties` field and pass `ship_with.type: "shipping_option_code"` in the request body.<br /><br />To understand what `shipping_option_code`s are available for your shipment, you can use the [Return a list of available shipping options](/api/v3/shipping-options/return-a-list-of-available-shipping-options) endpoint in the Shipping options API.<br /><br />If you have hardcoded your shipping methods on your system, you can use the [Compat API](/api/v3/compat/retrieve-a-list-of-shipping-options) to match your hardcoded shipping method IDs to the equivalent shipping option codes |
| Understand the pricing of the carrier service you'd like to use to ship your parcel                                                                                                                                                                                      | Use one of these v2 endpoints:<ul><li>[Retrieve a list of shipping products](/api/v2/shipping-products/retrieve-a-list-of-shipping-products), passing `contract_pricing: true` and the `contract` field (with your desired carrier contract ID) in the request body</li><li>[Retrieve a shipping price](/api/v2/shipping-prices/retrieve-a-shipping-price), passing the `from_country`, `shipping_method_id`, `weight`, `weight_unit` query parameters</li></ul>                                                   | Use the [Return a list of available shipping options](/api/v3/shipping-options/return-a-list-of-available-shipping-options) endpoint in the Shipping options API                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Define the address **from** which you'd like to ship                                                                                                                                                                                                                     | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API and either:<ul><li>Specify all fields prefixed with `from_` in the request body</li><li>Specify the `sender_address` field to use a sender address ID already saved in the Sendcloud system</li></ul>                                                                                                                                                                                                 | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and specify the `from_address` in the request body.<br /><br />Note that sender address IDs are not supported in the Shipments API v3.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Define the address **to** which you'd like to ship                                                                                                                                                                                                                       | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API and specify the `name`, `company_name`, `address`, `house_number`, `address_2`, `postal_code`, `city`, `to_post_number`, `country_state`, `country`, `email`, and `telephone` fields in the request body                                                                                                                                                                                              | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and specify the `to_address` in the request body                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Define the brand you want your parcel to be associated with                                                                                                                                                                                                              | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API and specify the `sender_address`.<br /><br />Note: In the Sendcloud Platform, one sender address ID can be linked to one brand. When announcing a parcel with that sender address ID, the associated brand will also be linked to the parcel. The same sender address ID cannot have multiple brands associated with it.                                                                              | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and specify the `brand_id` in the request body.<br /><br />To understand what brands are available for your shipment, you can use the [Retrieve a list of brands](/api/v2/brands/retrieve-a-list-of-brands) endpoint.                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Add insurance to your single-collo shipment                                                                                                                                                                                                                              | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API and specify the `insured_value` or `total_insured_value` fields in the request body                                                                                                                                                                                                                                                                                                                   | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and include the `additional_insured_price` field for each parcel in the request body.<br /><br />`additional_insured_price` is the amount for which you want to add additional insurance (on top of carrier insurance), equivalent to the `insured_value` field in the Parcels API v2<br /><br />The `total_insured_value` field is not supported in v3.                                                                                                                                                                                                                                                                                                       |
| Add insurance to your multicollo shipment                                                                                                                                                                                                                                | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API and specify the `insured_value` or `total_insured_value` fields in the request body.<br /><br />Note that each parcel must have the same insurance value.                                                                                                                                                                                                                                             | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and include the `additional_insured_price` field for each parcel in the request body.<br /><br />Unlike the Parcels API v2, each parcel can have a different insurance value.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Set parcel dimensions and weight for your single-collo shipment                                                                                                                                                                                                          | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API and specify the `weight`, `length`, `width`, and `height` fields in the request body                                                                                                                                                                                                                                                                                                                  | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and specify the `dimensions` and `weight` fields for each parcel in the request body.<br /><br />You can also change the weight or dimensions units using these fields.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Set parcel dimensions and weight for your multicollo shipment                                                                                                                                                                                                            | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API and specify the `weight`, `length`, `width`, `height` fields in the request body.<br /><br />Note that each parcel must have the same weight and dimensions.                                                                                                                                                                                                                                          | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and specify the `dimensions` and `weight` fields for each parcel in the request body.<br /><br />Unlike the Parcels API v2, each parcel can have different dimensions and a different weight.                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Set the Checkout Delivery Method so any shipping rule based on it gets applied                                                                                                                                                                                           | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API and specify the `shipping_method_checkout_name` field in the request body                                                                                                                                                                                                                                                                                                                             | Use either the [synchronous](/api/v3/shipments/create-a-shipment-with-rules-and-or-default-and-announce-it-synchronously) or [asynchronous](/api/v3/shipments/create-a-shipment-with-rules-and-or-default-and-announce-it-asynchronously) Create a shipment with rules and/or defaults endpoints in the Shipments API and include the `delivery_indicator` field in the request body                                                                                                                                                                                                                                                                                                                                      |
| Assign a shipment UUID to your parcel to connect your parcels with the orders created via the [Create or update a list of shipments](/api/v2/integrations/create-a-list-of-shipments) endpoint in the Integrations API (only available for certified Sendcloud partners) | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API and specify the `shipment_uuid` field in the request body                                                                                                                                                                                                                                                                                                                                             | Not applicable.<br /><br />Orders are automatically associated with a shipment when announced via the the [Request a label for a single order synchronously](/api/v3/ship-an-order/request-a-label-for-a-single-order-synchronously) or [Request a label for one or more orders asynchronously](/api/v3/ship-an-order/request-a-label-for-one-or-more-orders-asynchronously) endpoints.                                                                                                                                                                                                                                                                                                                                   |
| Retrieve your label after announcement - Native ZPL label<sup>\*</sup>                                                                                                                                                                                                   | 🚫 Not supported                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Use one of these options:<ul><li>[Retrieve a parcel document](/api/v3/parcel-documents/retrieve-a-parcel-document), with the `type` path parameter set to `label` and the `Accept` header set to `application/zpl`</li><li>Use the response from [Create and announce a shipment synchronously](/api/v3/shipments/create-and-announce-a-shipment-synchronously) or [Create a shipment with rules and/or defaults and announce it synchronously](/api/v3/shipments/create-a-shipment-with-rules-and-or-default-and-announce-it-synchronously) (for **single-collo** shipments only)</li></ul>                                                                                                                              |
| Define a label note to either show on the label or on be communicated to the carrier without showing on the label (depending on the carrier)                                                                                                                             | 🚫 Not supported                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and specify the `label_notes` field for each parcel in the request body                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Set the SSCC field when shipping a pallete                                                                                                                                                                                                                               | 🚫 Not supported                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and specify the `sscc` field for each parcel in the request body                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Define when you'd like the shipment to be picked up by the carrier                                                                                                                                                                                                       | 🚫 Not supported                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and specify the `delivery_dates.handover_at` field in the request body                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| Define when you'd like the shipment to be delivered to your customer                                                                                                                                                                                                     | 🚫 Not supported                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Use any [Shipments API](/api/v3/shipments) `POST` endpoint and specify the `delivery_dates.deliver_at` field in the request body                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |

<sup>\*</sup> Native ZPL labels are only supported for a few selected carriers. As of 1/12/2025: Asendia, Bring, BRT,
Colis Privé, Colissimo, DHL eCommerce Benelux, DHL Germany, Inpost Poland, Ontime, PLX Parcel Logistics, Trunkrs, UPS

### Returns

In API v2, returns were handled via the Parcels API. In API v3, there is a dedicated Returns API to make managing returns easier. We've also introduced the possibility to **validate return shipments** before creating them.

| Action                           | API v2                                                                                                                                                                                                                                                                              | API v3                                                                                                                   |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Create a return (asynchronously) | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, passing `request_label_async: true`, `is_return: true`, setting the `from_`-prefixed fields in the request body, and setting a shipping method that supports returns. | Use the [Create a return](/api/v3/returns/create-a-return) endpoint in the Returns API                                   |
| Create a return (synchronously)  | Use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint in the Parcels API, passing `request_label_async: true`, `is_return: true`, setting the `from_`-prefixed fields in the request body, and setting a shipping method that supports returns. | Use the [Create a return synchronously](/api/v3/returns/create-a-return-synchronously) endpoint in the Returns API       |
| Retrieve a list of returns       | Use the [Retrieve parcels](/api/v2/parcels/retrieve-parcels) endpoint in the Parcels API                                                                                                                                                                                            | Use the [Retrieve a list of returns](/api/v3/returns/retrieve-a-list-of-returns) endpoint in the Returns API             |
| Retrieve a return                | Use the [Retrieve a parcel](/api/v2/parcels/retrieve-a-parcel) endpoint in the Parcels API                                                                                                                                                                                          | Use the [Retrieve a return](/api/v3/returns/retrieve-a-return) endpoint in the Returns API                               |
| Request cancellation of a return | Use the [Cancel a parcel](/api/v2/parcels/cancel-a-parcel) endpoint in the Parcels API                                                                                                                                                                                              | Use the [Request cancellation of a return](/api/v3/returns/request-cancellation-of-a-return) endpoint in the Returns API |
| Validate a return                | 🚫 Not supported                                                                                                                                                                                                                                                                    | Use the [Validate a return](/api/v3/returns/validate-a-return) endpoint in the Returns API                               |
| Retrieve a return portal URL     | Use the [Retrieve a return portal URL](/api/v2/parcels/retrieve-a-return-portal-url) endpoint in the Parcels API                                                                                                                                                                    | 🚫 Not supported yet, but implementation is ongoing.                                                                     |

### Contracts

In the v3 version of the Contracts API, we've added support for creating, updating, and deleting carrier contracts via the API.

| Action                        | Contracts API v2                                                                                   | Contracts API v3                                                                                                                                                                                                                                                  |
| ----------------------------- | -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| List all your contracts       | Use the v2 [Retrieve a list of contracts](/api/v2/contracts/retrieve-a-list-of-contracts) endpoint | Use the v3 [Retrieve a list of contracts](/api/v3/contracts/retrieve-a-list-of-contracts) endpoint.<br /><br />Unlike the Contracts API v2, this endpoint uses cursor-based pagination.                                                                           |
| Retrieve a specific contract  | Use the v2 [Retrieve a contract](/api/v2/contracts/retrieve-a-contract) endpoint                   | Use the v3 [Retrieve a contract](/api/v3/contracts/retrieve-a-contract) endpoint                                                                                                                                                                                  |
| Create a contract for carrier | 🚫 Not supported                                                                                   | Use the [Create a contract for a carrier](/api/v3/contracts/create-a-contract-for-a-carrier) endpoint.<br /><br />To help with creating contracts, use the [Retrieve a list of contract schemas](/api/v3/contracts/retrieve-a-list-of-contract-schemas) endpoint. |
| Update a contract             | 🚫 Not supported                                                                                   | Use the [Update a contract](/api/v3/contracts/update-a-contract) endpoint.<br /><br />To help with updating contracts, use the [Retrieve a list of contract schemas](/api/v3/contracts/retrieve-a-list-of-contract-schemas) endpoint.                             |
| Delete a contract             | 🚫 Not supported                                                                                   | Use the [Delete a contract](/api/v3/contracts/delete-a-contract) endpoint                                                                                                                                                                                         |

### Pickups

In the v3 version of the Pickups API, we've expanded support to include several new carriers that were not available in v2.

There have also been some field changes between the Pickups API v2 and Pickups API v3. Please refer to the [pickup fields section](#pickups-fields) for more details.

| Action                                | Pickups API v2                                                                               | Pickups API v3                                                                               |
| ------------------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| List all pickups                      | Use the v2 [Retrieve a list of pickups](/api/v2/pickups/retrieve-a-list-of-pickups) endpoint | Use the v3 [Retrieve a list of pickups](/api/v3/pickups/retrieve-a-list-of-pickups) endpoint |
| Get a specific pickup                 | Use the v2 [Retrieve a pickup](/api/v2/pickups/retrieve-a-pickup) endpoint                   | Use the v3 [Retrieve a pickup](/api/v3/pickups/retrieve-a-pickup) endpoint                   |
| Create a pickup for Correos Express   | Use the v2 [Create a pickup](/api/v2/pickups/create-a-pickup) endpoint                       | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for DHL               | Use the v2 [Create a pickup](/api/v2/pickups/create-a-pickup) endpoint                       | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for DHL Parcel Iberia | Use the v2 [Create a pickup](/api/v2/pickups/create-a-pickup) endpoint                       | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for DPD               | Use the v2 [Create a pickup](/api/v2/pickups/create-a-pickup) endpoint                       | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for FedEx             | Use the v2 [Create a pickup](/api/v2/pickups/create-a-pickup) endpoint                       | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for Poste Italiane    | Use the v2 [Create a pickup](/api/v2/pickups/create-a-pickup) endpoint                       | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for UPS               | Use the v2 [Create a pickup](/api/v2/pickups/create-a-pickup) endpoint                       | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for BRT               | 🚫 Not supported                                                                             | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for DPD AT            | 🚫 Not supported                                                                             | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for DHL DE            | 🚫 Not supported                                                                             | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for DHL Express       | 🚫 Not supported                                                                             | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for DHL Parcel GB     | 🚫 Not supported                                                                             | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for GLS Italy         | 🚫 Not supported                                                                             | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |
| Create a pickup for Hermes Germany    | 🚫 Not supported                                                                             | Use the v3 [Create a pickup](/api/v3/pickups/create-a-pickup) endpoint                       |

### Tracking

The Tracking API v2 is replaced with the Parcel tracking API v3, which has an improved response structure, and supports creating external tracking parcels.

| Action                                 | Tracking API v2                                                                                                          | Parcel tracking API v3                                                                                                            |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| Get tracking information for a parcel  | Use the [Retrieve tracking information of a parcel](/api/v2/tracking/retrieve-tracking-information-of-a-parcel) endpoint | Use the [Retrieve tracking information for a parcel](/api/v3/parcel-tracking/retrieve-tracking-information-for-a-parcel) endpoint |
| Create an external parcel for tracking | 🚫 Not supported                                                                                                         | Use the [Create an external parcel for tracking](/api/v3/parcel-tracking/create-an-external-parcel-for-tracking) endpoint         |

### Dynamic Checkout

The Dynamic Checkout API v2 is replaced with the Dynamic Checkout API v3, which contains references to the Shipments API v3 instead of the Parcels API v2, and can be used with codes from the Shipping options API. Error responses also now comply with the [JSON:API standard for error objects](https://jsonapi.org/format/#error-objects).

| Action                                                                 | Dynamic Checkout API v2                                                                                                 | Dynamic Checkout API v3                                                                                                 |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Get a list of delivery options to display in your shop's checkout page | Use the v2 [Retrieve a list of delivery options](/api/v2/dynamic-checkout/retrieve-a-list-of-delivery-options) endpoint | Use the v3 [Retrieve a list of delivery options](/api/v3/dynamic-checkout/retrieve-a-list-of-delivery-options) endpoint |

### Analytics

The Analytics API v2 is replaced with the Analytics API v3 (BETA). Endpoints now live under `/analytics/...` instead of `/insights/...`, accept arrays for the carrier, shipping option, and country filters, and shipping methods are replaced by shipping options. Country filters are renamed `from_country_code` / `to_country_code` to match other v3 APIs.

| Action                                 | Analytics API v2                                                                                                       | Analytics API v3                                                                                                       |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Retrieve carrier transit times         | Use the v2 [Retrieve carrier transit times](/api/v2/analytics/retrieve-carrier-transit-times) endpoint                 | Use the v3 [Retrieve carrier transit times](/api/v3/analytics/retrieve-carrier-transit-times) endpoint                 |
| Retrieve shipping option transit times | Use the v2 [Retrieve shipping method transit times](/api/v2/analytics/retrieve-shipping-method-transit-times) endpoint | Use the v3 [Retrieve shipping option transit times](/api/v3/analytics/retrieve-shipping-option-transit-times) endpoint |

### Reporting

The Reporting API v2 is replaced with the Reporting API v3, which references shipping options instead of shipping methods, uses `from_address_*` / `to_address_*` field naming to match other v3 APIs, and returns errors in the [JSON:API format](https://jsonapi.org/format/#error-objects).

There have also been some field changes between the Reporting API v2 and Reporting API v3. Please refer to the [reporting fields section](#reporting-fields) for more details.

| Action                    | Reporting API v2                                                                             | Reporting API v3                                                                             |
| ------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Create a parcels report   | Use the v2 [Create a parcels report](/api/v2/reporting/create-a-parcels-report) endpoint     | Use the v3 [Create a parcels report](/api/v3/reporting/create-a-parcels-report) endpoint     |
| Retrieve a parcels report | Use the v2 [Retrieve a parcels report](/api/v2/reporting/retrieve-a-parcels-report) endpoint | Use the v3 [Retrieve a parcels report](/api/v3/reporting/retrieve-a-parcels-report) endpoint |

## What stayed the same?

### Webhooks

There are no changes to webhooks between API v2 and API v3.

Additionally, the new [Event Subscriptions API](/api/v3/event-subscriptions/index) (BETA) provides a programmatic alternative for subscribing to parcel events. It supports multiple connection types (webhook, Klaviyo) and configurable authentication, giving you more flexibility than the classic webhook setup.

### API v2 endpoints that are compatible with API v3

Some API v2 endpoints don't yet have an API v3 equivalent, but can still be used together with any API v3 endpoint. Here's a list of those endpoints:

* [Brands API](/api/v2/brands/retrieve-a-list-of-brands)
* [Invoices API](/api/v2/invoices)
* [Parcel statuses API](/api/v2/parcel-statuses)
* [Return portal API](/api/v2/return-portal)
* [Service points API](/api/v2/service-points)
* [Users API](/api/v2/users/retrieve-your-user-data)

## Field changes between API v2 and API v3

### Shipment/Parcel fields

| Parcels API v2               | API v3                             |
| ---------------------------- | ---------------------------------- |
| `order_number`               | `order_number`                     |
| `contract`                   | `ship_with.properties.contract_id` |
| `total_order_value_currency` | `total_order_price.currency`       |
| `total_order_value`          | `total_order_price.value`          |
| `external_reference`         | `external_reference_id`            |
| `reference`                  | `reference`                        |
| `to_service_point`           | `to_service_point.id`              |

### Address fields

| Parcels API v2      | API v3                             |
| ------------------- | ---------------------------------- |
| `name`              | `to_address.name`                  |
| `company_name`      | `to_address.company_name`          |
| `address`           | `to_address.address_line_1`        |
| `house_number`      | `to_address.house_number`          |
| `address_2`         | `to_address.address_line_2`        |
| `postal_code`       | `to_address.postal_code`           |
| `city`              | `to_address.city`                  |
| `to_post_number`    | `to_address.po_box`                |
| `country_state`     | `to_address.state_province_code`   |
| `country`           | `to_address.country_code`          |
| `email`             | `to_address.email`                 |
| `telephone`         | `to_address.phone_number`          |
| `from_name`         | `from_address.name`                |
| `from_company_name` | `from_address.company_name`        |
| `from_address_1`    | `from_address.address_line_1`      |
| `from_house_number` | `from_address.house_number`        |
| `from_address_2`    | `from_address.address_line_2`      |
| `from_postal_code`  | `from_address.postal_code`         |
| `from_city`         | `from_address.city`                |
| 🚫 Not supported    | `from_address.po_box`              |
| 🚫 Not supported    | `from_address.state_province_code` |
| `from_country`      | `from_address.country_code`        |
| `from_email`        | `from_address.email`               |
| `from_telephone`    | `from_address.phone_number`        |

### Parcel item fields

| Parcels API v2                  | Shipments API v3                                                                                                       |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `parcel_items.hs_code`          | `parcels.parcel_items.hs_code`                                                                                         |
| `parcel_items.weight`           | `parcels.parcel_items.weight.value`                                                                                    |
| 🚫 Not supported                | `parcels.parcel_items.weight.unit`                                                                                     |
| `parcel_items.quantity`         | `parcels.parcel_items.quantity`                                                                                        |
| `parcel_items.description`      | `parcels.parcel_items.description`                                                                                     |
| `parcel_items.origin_country`   | `parcels.parcel_items.origin_country`                                                                                  |
| `parcel_items.value`            | `parcels.parcel_items.price.value`                                                                                     |
| 🚫 Not supported                | `parcels.parcel_items.price.currency`                                                                                  |
| `parcel_items.sku`              | `parcels.parcel_items.sku`                                                                                             |
| `parcel_items.product_id`       | `parcels.parcel_items.product_id`                                                                                      |
| `parcel_items.properties`       | `parcels.parcel_items.properties`                                                                                      |
| `parcel_items.item_id`          | `parcels.parcel_items.item_id`                                                                                         |
| `parcel_items.return_reason`    | Not applicable, as in v3 returns are created via the Returns API v3. [More context on how to create returns](#returns) |
| `parcel_items.return_message`   | Not applicable, as in v3 returns are created via the Returns API v3. [More context on how to create returns](#returns) |
| `parcel_items.mid_code`         | `parcels.parcel_items.mid_code`                                                                                        |
| `parcel_items.material_content` | `parcels.parcel_items.material_content`                                                                                |
| `parcel_items.intended_use`     | `parcels.parcel_items.intended_use`                                                                                    |
| `parcel_items.dangerous_goods`  | `parcels.parcel_items.dangerous_goods`                                                                                 |

### Shipping methods vs. Shipping products vs. Shipping prices vs. Shipping options fields

| Shipping methods API v2 | Shipping products API v2  | Shipping prices API v2          | Shipping options API v3                           |
| ----------------------- | ------------------------- | ------------------------------- | ------------------------------------------------- |
| `from_postal_code`      | `from_postal_code`        | `from_postal_code`              | `from_postal_code`                                |
| `is_return`             | `returns`                 | 🚫 Not supported                | `functionalities.returns`                         |
| `sender_address`        | 🚫 Not supported          | 🚫 Not supported                | 🚫 Not supported                                  |
| `service_point_id`      | 🚫 Not supported          | 🚫 Not supported                | `to_service_point_id`                             |
| `to_country`            | `to_country`              | `to_country`                    | `to_country_code`                                 |
| `to_postal_code`        | `to_postal_code`          | `to_postal_code`                | `to_postal_code`                                  |
| 🚫 Not supported        | `carrier`                 | 🚫 Not supported                | `carrier_code`                                    |
| 🚫 Not supported        | `contract`                | `contract`                      | `contract_id`                                     |
| 🚫 Not supported        | `contract_pricing`        | Pricing is always calculated    | `calculate_quotes`                                |
| 🚫 Not supported        | `height`                  | 🚫 Not supported                | `parcels.dimensions.height`                       |
| 🚫 Not supported        | `height_unit`             | 🚫 Not supported                | `parcels.dimensions.unit`                         |
| 🚫 Not supported        | `length`                  | 🚫 Not supported                | `parcels.dimensions.length`                       |
| 🚫 Not supported        | `length_unit`             | 🚫 Not supported                | `parcels.dimensions.unit`                         |
| 🚫 Not supported        | `width`                   | 🚫 Not supported                | `parcels.dimensions.width`                        |
| 🚫 Not supported        | `width_unit`              | 🚫 Not supported                | `parcels.dimensions.unit`                         |
| 🚫 Not supported        | `lead_time_hours`         | 🚫 Not supported                | `lead_time`                                       |
| 🚫 Not supported        | `weight`                  | `weight` (Required)             | `parcels.weight.value`                            |
| 🚫 Not supported        | `weight_unit`             | `weight_unit` (Required)        | `parcels.weight.unit`                             |
| 🚫 Not supported        | `from_country` (Required) | `from_country` (Required)       | `from_country_code`                               |
| 🚫 Not supported        | 🚫 Not supported          | `shipping_method_id` (Required) | `shipping_product_code` OR `shipping_option_code` |
| 🚫 Not supported        | 🚫 Not supported          | 🚫 Not supported                | `parcels.additional_insured_price`                |
| 🚫 Not supported        | 🚫 Not supported          | 🚫 Not supported                | `parcels.total_insured_price`                     |
| 🚫 Not supported        | 🚫 Not supported          | 🚫 Not supported                | `functionalities`                                 |

### Customs fields

| Parcels API v2                      | Shipments API v3                                                                                                       |
| ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `customs_invoice_nr`                | `invoice_number`                                                                                                       |
| `customs_shipment_type`             | `export_reason`                                                                                                        |
| `export_type`                       | `export_type`                                                                                                          |
| `invoice_date`                      | `invoice_date`                                                                                                         |
| `discount_granted`                  | `discount_granted`                                                                                                     |
| `freight_costs`                     | `freight_costs`                                                                                                        |
| `insurance_costs`                   | `insurance_costs`                                                                                                      |
| `other_costs`                       | `other_costs`                                                                                                          |
| `general_notes`                     | `general_notes`                                                                                                        |
| `additional_declaration_statements` | `additional_declaration_statements`                                                                                    |
| `importer_of_record`                | `importer_of_record`                                                                                                   |
| `tax_numbers`                       | `tax_numbers`                                                                                                          |
| `return_data`                       | Not applicable as in v3, returns are created via the Returns API v3. [More context on how to create returns](#returns) |

### Contracts fields

| Contracts API v2 | Contracts API v3         |
| ---------------- | ------------------------ |
| `carrier`        | `carrier_code`           |
| `client_id`      | `client_id`              |
| `country`        | `country_code`           |
| `is_active`      | `is_active`              |
| `name`           | `name`                   |
| `is_default`     | `is_default_per_carrier` |

### Pickups fields

| Pickups API v2         | Pickups API v3                                                                        |
| ---------------------- | ------------------------------------------------------------------------------------- |
| `id`                   | 🚫 Not supported                                                                      |
| `carrier`              | `carrier_code`                                                                        |
| `country`              | `address.country_code`                                                                |
| `city`                 | `address.city`                                                                        |
| `name`                 | `address.name`                                                                        |
| `country_state`        | `address.state_province_code`                                                         |
| `company_name`         | `address.company_name`                                                                |
| `email`                | `address.email`                                                                       |
| `address`              | `address.address_line_1`                                                              |
| `address_2`            | `address.address_line_2`                                                              |
| `postal_code`          | `address.postal_code`                                                                 |
| `telephone`            | `address.phone_number`                                                                |
| 🚫 Not supported       | House number should be provided as part of the address field (`address.house_number`) |
| 🚫 Not supported       | `address.po_box`                                                                      |
| `quantity`             | `items.quantity`                                                                      |
| `total_weight`         | `items.total_weight.value`                                                            |
| 🚫 Not supported       | `items.total_weight.unit`                                                             |
| 🚫 Not supported       | `items.container_type`                                                                |
| `reference`            | `reference`                                                                           |
| `special_instructions` | `special_instructions`                                                                |
| `tracking_number`      | 🚫 Not supported                                                                      |
| `pickup_from`          | `time_slots.start_at`                                                                 |
| `pickup_until`         | `time_slots.end_at`                                                                   |
| `pickup_status`        | 🚫 Not supported                                                                      |
| `created_at`           | 🚫 Not supported                                                                      |
| `cancelled_at`         | 🚫 Not supported                                                                      |
| `contract`             | `contract_id`                                                                         |

### Reporting fields

The values you can pass in the `fields` array and the columns that appear in the CSV have been renamed to match the rest of the v3 APIs.

| Reporting API v2                               | Reporting API v3                                                                |
| ---------------------------------------------- | ------------------------------------------------------------------------------- |
| `from_company_name`                            | `from_address_company_name`                                                     |
| `origin_city`                                  | `from_address_city`                                                             |
| `origin_postal_code`                           | `from_address_postal_code`                                                      |
| `origin_country_code`                          | `from_address_country_code`                                                     |
| `origin_country_name`                          | `from_address_country_name`                                                     |
| `destination_city`                             | `to_address_city`                                                               |
| `destination_postal_code`                      | `to_address_postal_code`                                                        |
| `destination_country_code`                     | `to_address_country_code`                                                       |
| `destination_country_name`                     | `to_address_country_name`                                                       |
| `shipping_method`                              | `shipping_option_code`                                                          |
| `shipping_method_name`                         | 🚫 Not supported                                                                |
| `price`                                        | `total_cost`                                                                    |
| `global_status_slug`, `carrier_status`         | `status` (merges the global and carrier-reported status into one field)         |
| `global_sub_status_slug`, `carrier_sub_status` | `sub_status` (merges the global and carrier-reported sub-status into one field) |
| `arrived_at`                                   | `delivered_at`                                                                  |
| `first_delivery_at`                            | `first_offer_at`                                                                |
| `created_at`                                   | 🚫 Not supported (use `announced_at`)                                           |
| `updated_at`                                   | 🚫 Not supported                                                                |

The `filters` object follows the same renames where applicable. `announced_after` and `announced_before` are now required.

### Dynamic Checkout fields

| API v2      | API v3                                                        |
| ----------- | ------------------------------------------------------------- |
| `method_id` | Use `checkout_identifier` with `shipping_option_code` instead |

### Sender address fields

| Parcels API           | Shipments API                                                                       |
| --------------------- | ----------------------------------------------------------------------------------- |
| `city`                | `city`                                                                              |
| `company_name`        | `company_name`                                                                      |
| `contact_name`        | `name`                                                                              |
| `country`             | `country_code`                                                                      |
| `country_state`       | `state_province_code`                                                               |
| `email`               | `email`                                                                             |
| `house_number`        | `house_number`                                                                      |
| `id`                  | `id`                                                                                |
| `postal_box`          | `po_box`                                                                            |
| `postal_code`         | `postal_code`                                                                       |
| `street`              | `address_line_1`                                                                    |
| `telephone`           | `phone_number`                                                                      |
| `vat_number`          | `tax_numbers` object `tax_number.name` `tax_number.country_code` `tax_number.value` |
| `eori_number`         | `tax_numbers` object `tax_number.name` `tax_number.country_code` `tax_number.value` |
| 🚫 Not supported      | `tax_numbers`                                                                       |
| 🚫 Not supported      | `brand_id`                                                                          |
| 🚫 Not supported      | `label`                                                                             |
| `signature_full_name` | `signature` object with `signature.full_name`                                       |
| `signature_initials`  | `signature` object with `signature.initials`                                        |
| 🚫 Not supported      | `address_line_2`                                                                    |


> ## Documentation Index
> Fetch the complete documentation index at: https://sendcloud.dev/llms.txt
> Use this file to discover all available pages before exploring further.

# Shipping rates

<Warning>
  This page applies to v2 of the Sendcloud API and is no longer maintained. To learn more about switching to API v3,
  read our [migration guide](/docs/getting-started/migration-guidelines-for-api-v3#parcels/shipments).
</Warning>

The Sendcloud API seamlessly connects you to [a huge range of carriers worldwide](https://www.sendcloud.com/carriers/), giving you access to a diverse catalogue of shipping methods and service levels to fit the needs of any e-commerce business. We're continuously integrating new carriers and methods with our platform across the national and international delivery landscape.

## Receive discounts on your shipping labels

You don't need to have a carrier contract to access shipping methods in Sendcloud. You can create shipping labels using Sendcloud rates, and receive a discount on your label price based on your subscription plan. The higher your plan, the more discount you'll receive.

## Connect your own direct contract

If you have a direct contract with a carrier, you can [add it to your Sendcloud account](/docs/getting-started/carrier-contracts/) and create labels in Sendcloud using your contracted rates.

## Retrieve shipping rates through the API

Through the Sendcloud API, you can access rates for a host of shipping methods, and directly compare pricing for domestic and international delivery options in a single API call.

<Note>
  You'll only be able to see rates for carriers you've enabled in your account, so be sure to complete all the steps in
  [Getting started](/docs/getting-started/) before proceeding.
</Note>

### Get rates for all shipping methods

If you don't know which method you want to use, or if you want to compare pricing, you can retrieve a list of all available methods and rates by making a `GET` request to the [Retrieve a list of shipping methods](/api/v2/shipping-methods/retrieve-a-list-of-shipping-methods) endpoint.

<Card title="Shipping methods" icon="truck-fast" href="/docs/shipping/shipping-methods" horizontal>
  Learn more in our shipping methods guide
</Card>

### Get rates for specific shipping methods

<Warning>
  Note: Carriers that use pricing based on shipping zones (e.g. Spanish carriers who charge different rates based on the
  postal code of the shipment) are not supported.
</Warning>

You can access rates for a specific shipping method by making a `GET` request to the [Retrieve a shipping price](/api/v2/shipping-prices/retrieve-a-shipping-price) endpoint.

You'll need to know some basic information before you can make your request:

1. The shipping method `id`, which will be used as the `shipping_method_id` query parameter. This is the internal reference Sendcloud uses to identify shipping methods. You can retrieve an `id` via the [Retrieve a list of shipping methods](/api/v2/shipping-methods/retrieve-a-list-of-shipping-methods) or Shipping products endpoints.
2. The `weight` of your parcel, and whether it's in kilograms or grams (`weight_unit`)
3. The country the parcel will be sent from (`from_country`) as an [ISO 3166-1 alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2) country code, e.g. `NL` for the Netherlands
4. (Optional) The country the parcel will be sent to (`to_country`) as an [ISO 3166-1 alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2) country code
   * If you don't provide a `to_country` parameter, the response will include prices for all the shipping destinations that are applicable to the method

These pieces of information should be sent as query parameters to the endpoint, for example:

```http Request method and URL wrap theme={null}
GET https://panel.sendcloud.sc/api/v2/shipping-price/?shipping_method_id=1234&weight=2weight_unit=kilogram&from_country=NL&to_country=DE
```

<Note>
  **Tip:** If you've already connected your own carrier contract, then rates for your connected carriers will be null,
  unless you have [uploaded your own contract
  pricing](https://support.sendcloud.com/hc/en-us/articles/5163547066004-How-to-upload-your-own-prices-from-your-direct-carrier-contract).
</Note>

<Card title="Shipping prices API" icon="dollar-sign" href="/api/v2/shipping-prices/retrieve-a-shipping-price" horizontal>
  Retrieve a shipping price endpoint
</Card>


> ## Documentation Index
> Fetch the complete documentation index at: https://sendcloud.dev/llms.txt
> Use this file to discover all available pages before exploring further.

# Retrieve a shipping price

> Retrieve shipping rate information for a specific `shipping_method_id` and `from_country`.

<Warning>
  **API v2 is entering maintenance mode.** New users should start with API v3 to access our latest features and improved performance. Already using v2? Don't worry, your current integration remains fully functional. Read more about [maintenance mode](/docs/getting-started/api-version-guide), or check out the [migration guide for API v3](/docs/getting-started/migration-guidelines-for-api-v3).
</Warning>

For users that have uploaded their own prices, the response will show the prices that have been uploaded.

The response is an array of prices for all available receiver countries. If the `to_country` query parameter is present, the array will only contain one item.

Note that `price` and `currency` will be `null` when no pricing is available for a receiver country.

<Warning>
  If you have more than one active contract for a specific carrier, you must fill the `contract` attribute with your desired contract ID in your request. You can get your contract ID from the [Retrieve a list of contracts](/api/v2/contracts/retrieve-a-list-of-contracts) endpoint.
</Warning>

<Info>
  In order to view **remote surcharges**, you are required to provide the `to_country` and `to_postal_code`. Similarly, to access **zonal prices**, you need to provide `to_country`, `from_postal_code` and `to_postal_code`. This information ensures accurate and customized pricing based on the specific location, enabling you to understand any additional charges associated with remote areas and access pricing based on their designated zones.
</Info>


## OpenAPI

````yaml /.openapi/v2/shipping-price/openapi.yaml get /shipping-price
openapi: 3.1.0
info:
  title: Shipping price
  version: 2.0.0
  description: >-
    The Shipping prices API allows you to retrieve rates for a specific shipping
    method based on the specified `shipping_method_id`.
  contact:
    name: Sendcloud API Support
    url: https://www.sendcloud.dev
    email: contact@sendcloud.com
  license:
    name: Apache 2.0
    url: https://www.apache.org/licenses/LICENSE-2.0.html
servers:
  - url: https://panel.sendcloud.sc/api/v2
    description: Sendcloud Production
security: []
tags:
  - name: Shipping price
paths:
  /shipping-price:
    parameters: []
    get:
      tags:
        - Shipping price
      summary: Retrieve a shipping price
      description: >-
        Retrieve shipping rate information for a specific `shipping_method_id`
        and `from_country`.
      operationId: sc-public-v2-scp-get-shipping_price
      parameters:
        - $ref: '#/components/parameters/shipping_method_id'
        - $ref: '#/components/parameters/from_country'
        - $ref: '#/components/parameters/to_country'
        - $ref: '#/components/parameters/weight'
        - $ref: '#/components/parameters/weight_unit'
        - $ref: '#/components/parameters/contract'
        - $ref: '#/components/parameters/from_postal_code'
        - $ref: '#/components/parameters/to_postal_code'
      responses:
        '200':
          $ref: '#/components/responses/200'
        '400':
          $ref: '#/components/responses/400'
      security:
        - HTTPBasicAuth: []
        - OAuth2ClientCreds: []
components:
  parameters:
    shipping_method_id:
      schema:
        type: integer
      in: query
      name: shipping_method_id
      description: >-
        The id of the shipping method retrieved via [shipping
        products](/api/v2/shipping-products/retrieve-a-list-of-shipping-products)
        or [shipping
        methods](/api/v2/shipping-methods/retrieve-a-list-of-shipping-methods).
      required: true
    from_country:
      schema:
        type: string
      in: query
      name: from_country
      description: >-
        The sender country of the shipment, as an [ISO 3166-1
        alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2).
      required: true
    to_country:
      schema:
        type: string
      in: query
      name: to_country
      description: >-
        The receiver country of the shipment, as an [ISO 3166-1
        alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2). Required if
        the carrier is zonal. Also required to see if remote surcharges apply.
    weight:
      schema:
        type: integer
      in: query
      name: weight
      description: The weight of the shipment, in weight_unit.
      required: true
    weight_unit:
      schema:
        type: string
      in: query
      name: weight_unit
      description: One of `kilogram` or `gram`.
      required: true
    contract:
      name: contract
      in: query
      required: false
      schema:
        type: integer
        minimum: 1
        example: 123
      description: >-
        Id of the contract that you would like to use to get the price. If you
        are requesting price for a direct contract then you need to upload your
        own price via the Sendcloud platform.
    from_postal_code:
      name: from_postal_code
      in: query
      required: false
      schema:
        type: string
        maxLength: 12
        example: '01000'
      description: Postal code of the sender. Required if the carrier is zonal.
    to_postal_code:
      name: to_postal_code
      in: query
      required: false
      schema:
        type: string
        maxLength: 12
        example: '01000'
      description: >-
        Postal code of the recipient. Required if the carrier is zonal. Also
        required to see if remote surcharges apply.
  responses:
    '200':
      description: OK
      content:
        application/json:
          schema:
            type: array
            items:
              $ref: '#/components/schemas/ShippingPrice'
          examples:
            RetrieveShippingPrices:
              $ref: '#/components/examples/ShippingPrice'
              summary: Shipping prices
            NotPrices:
              $ref: '#/components/examples/NoPrice'
              summary: No prices available
            NoData:
              $ref: '#/components/examples/NoData'
              summary: No data available
    '400':
      description: Bad Request
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
          examples:
            BadRequest:
              $ref: '#/components/examples/required_field_error'
              summary: Bad Request
  schemas:
    ShippingPrice:
      type: object
      description: Shipping price response
      properties:
        price:
          type: string
          description: Shipping price
          format: currency
          example: '6.50'
          nullable: true
        currency:
          type: string
          description: 3 letter currency code as defined by ISO-4217
          example: EUR
          format: iso-4217
          nullable: true
        to_country:
          type: string
          description: >-
            The receiver country of the shipment, as an [ISO 3166-1
            alpha-2](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2)
          example: NL
          format: iso 3166-1
        breakdown:
          $ref: '#/components/schemas/shipping-price-breakdown'
    Error:
      type: object
      description: Error response for shipping price
      properties:
        error:
          type: object
          properties:
            request:
              type: string
              format: uri-reference
              example: api/v2/shipping-price/
              description: The requested URL
            code:
              type: integer
              format: int32
              example: 400
              description: Code of the error
            message:
              type: string
              example: Bad request
              description: Description of the error
    shipping-price-breakdown:
      title: Shipping Price Breakdown Object
      description: A Sendcloud shipping price breakdown.
      type: array
      items:
        type: object
        properties:
          type:
            type: string
            example: price_without_insurance
            description: Type of the price. It is an identifier of category of the price.
          label:
            type: string
            example: Initial price per parcel
            description: >-
              This label is a friendly name for type of the price type and can
              be used to represent it.
          value:
            type: number
            format: float
            example: 6.4
            description: Price amount of the breakdown item.
  examples:
    ShippingPrice:
      summary: Shipping price
      value:
        - price: '6.50'
          currency: EUR
          to_country: NL
          breakdown:
            - type: price_without_insurance
              label: Label
              value: 6.5
    NoPrice:
      summary: No prices
      value:
        - price: null
          currency: null
          to_country: BE
    NoData:
      summary: No data
      value: []
    required_field_error:
      value:
        error:
          code: 400
          request: api/v2/shipping-price/
          message: 'shipping_method_id: "This field is required."'
  securitySchemes:
    HTTPBasicAuth:
      type: http
      description: >-
        Basic Authentication using API key and secrets is currently the main
        authentication mechanism.
      scheme: basic
    OAuth2ClientCreds:
      type: oauth2
      description: >-
        OAuth2 is a standardized protocol for authorization that allows users to
        share their private resources stored on one site with another site
        without having to provide their credentials. OAuth2 Client Credentials
        Grant workflow. This workflow is typically used for server-to-server
        interactions that require authorization to access specific resources.
      flows:
        clientCredentials:
          tokenUrl: https://account.sendcloud.com/oauth2/token/
          scopes:
            api: Default OAuth scope required to access Sendcloud API.

````


> ## Documentation Index
> Fetch the complete documentation index at: https://sendcloud.dev/llms.txt
> Use this file to discover all available pages before exploring further.

# Create a parcel

<Warning>
  This page applies to v2 of the Sendcloud API and is no longer maintained. To learn more about switching to API v3,
  read our [migration guide](/docs/getting-started/migration-guidelines-for-api-v3#parcels/shipments).
</Warning>

Sendcloud's flexible shipping API covers every part of the shipping process, from label creation right up to the point of delivery. Ready to put your shipping processes on autopilot? Read on to learn how to create your first parcel with Sendcloud's **Shipping API**.

There are two ways to create a parcel via the API:

**Method 1: Create a parcel object**

* This is the most flexible means of creating a parcel. The parcel object is created in the Sendcloud system, but the parcel is not immediately announced with the carrier.
* This gives you time to continue making changes to the parcel data and decide on a shipping method right up until the moment you're ready to create the label.
* Parcels can be processed either via the [Sendcloud platform](https://support.sendcloud.com/hc/en-us/articles/360025263691-Process-your-orders-), or you can perform all interactions via the API, depending on your specific use case.

**Method 2: (Advanced option): Create the parcel and shipping label in a single API call**

* This method is described in more detail at the end of this tutorial.

To help get you started, this guide will cover the basics of **creating a parcel via the API**, step-by-step.

Once the parcel is created, you can continue on to the next steps to learn how to choose a shipping method and print the label.

## Before you begin

1. Make sure you've completed basic account set up. See [Quickstart](/docs/getting-started)
2. You'll need to have obtained your API keys so you can authenticate with our API. See [Authentication](/docs/getting-started/authentication)
3. You'll need access to a tool that allows you to make API calls. Examples are [Postman](https://www.postman.com/sendcloud-api) and [Insomnia](https://insomnia.rest/download).

### The Create a parcel or parcels API endpoint

Parcels are created by sending a HTTP `POST` request to the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint.

```http Request method and URL theme={null}
POST https://panel.sendcloud.sc/api/v2/parcels
```

#### Authorization header

Every time you make an API call, you need to [authenticate](/docs/getting-started/authentication) your connection to Sendcloud by including your API keys through a HTTP header.

```http Authorization header theme={null}
Authorization: Basic <credentials>
```

## Step 1: Prepare your request

In the body of your HTTP request, you need to specify all the required information for the shipping label. Below you can find an example which will create a parcel object in your Sendcloud account.

```json Example request body theme={null}
{
  "parcel": {
    "name": "John Doe",
    "company_name": "FlowerShop",
    "email": "john@doe.com",
    "telephone": "+31611223344",
    "address": "Fürstenrieder Str.",
    "house_number": "70",
    "address_2": "",
    "city": "Munich",
    "country": "DE",
    "postal_code": "80686",
    "country_state": null,
    "to_service_point": 10168633,
    "to_post_number": 262373726,
    "customs_invoice_nr": "",
    "customs_shipment_type": null,
    "parcel_items": [
      {
        "description": "T-Shirt",
        "hs_code": "6109",
        "origin_country": "SE",
        "product_id": "898678671",
        "properties": {
          "color": "Blue",
          "size": "Medium"
        },
        "quantity": 2,
        "sku": "TST-OD2019-B620",
        "value": "19.95",
        "weight": "0.9"
      },
      {
        "description": "Laptop",
        "hs_code": "84713010",
        "origin_country": "DE",
        "product_id": "5756464758",
        "properties": {
          "color": "Black",
          "internal_storage": "2TB"
        },
        "quantity": 1,
        "sku": "LT-PN2020-B23",
        "value": "876.97",
        "weight": "1.69"
      }
    ],
    "weight": "3.49",
    "length": "31.5",
    "width": "27.2",
    "height": "12.7",
    "total_order_value": "896.92",
    "total_order_value_currency": "EUR",
    "shipment": {
      "id": 1316,
      "name": "DHL Parcel Connect 2-5kg to ParcelShop"
    },
    "shipping_method_checkout_name": "Battery WarehouseX DHL",
    "sender_address": 1,
    "quantity": 1,
    "total_insured_value": 0,
    "is_return": false,
    "request_label": false,
    "apply_shipping_rules": false,
    "request_label_async": false
  }
}
```

<Note>
  The important thing to note here is that the `request_label` parameter is set to `false`. This allows you to create a
  parcel without announcing it to a carrier or creating a shipping label.
</Note>

The parcel will be created using the **default** shipping method you saved in your account, and can be updated later.

Also note that specific carriers might impose [additional requirements on address-related fields](/docs/shipping/address-field-limits/).

### Other request fields

There are many other additional fields that you can specify when creating a parcel. An example would be the `sender_address` parameter which lets you ship a parcel from a different sender location, or the parameters related to customs information for international shipping.

You can find a list of the supported fields in our [API reference](/api/v2/parcels/create-a-parcel-or-parcels/).

## Step 2: Send your request

Take the example above, and use it to make a `POST` request to `http://panel.sendcloud.sc/api/v2/parcels`.

```http Request method, URL, and Authorization header theme={null}
POST https://panel.sendcloud.sc/api/v2/parcels
Authorization: Basic <base64-encoded-token>
```

If everything went well, you'll receive a HTTP 200 [status code](https://en.wikipedia.org/wiki/List_of_HTTP_status_codes) and a `parcel` object in the response body.

See an example of the response body in the [API reference](/api/v2/parcels/create-a-parcel-or-parcels).

#### Some things to note about the response

* The newly-created parcel will be assigned a parcel `id`, e.g. `"id": 189169249`. This is the unique parcel identifier which we will use whenever we want to update a parcel or create the label via the API.
* The current status of the newly-created parcel will be `"No label"`. It will appear in the Sendcloud platform under the **Incoming order view** with the message **Ready to process** until we create a label for it.
  <img src="https://mintcdn.com/sendcloud/1qLmoV2zg9wO4FD0/images/docs/shipping/create-a-label-guide.jpg?fit=max&auto=format&n=1qLmoV2zg9wO4FD0&q=85&s=db8b2601bb59b45d32d2e495f34e22cd" alt="Screenshot of the Incoming order view, showing the newly-created parcel with the status &#x22;Ready to process&#x22;" width="1918" height="610" data-path="images/docs/shipping/create-a-label-guide.jpg" />

## Step 3: Create the shipping label

To create shipping labels via the API, you need to use the [Update a parcel endpoint](/api/v2/parcels/update-a-parcel) to update the value of `request_label` to `true`.

Via this endpoint, you can also make changes to any of the properties that can be used for creating a parcel.

### Generating a label for an existing parcel

In this example, we will update parcel `"id": 1` as follows:

* Create the shipping label by providing the data `"request_label": true`
* Change the `name` of the recipient to a new value
* Change the shipping method by providing the corresponding `id`. In this example, we'll be using the method **"Unstamped letter"** to create a test label.

<Tip>
  You'll be invoiced for any shipping labels you create if you don't cancel or delete them within the [cancellation
  deadline](https://support.sendcloud.com/hc/en-us/articles/360025143991-How-do-I-cancel-my-shipment). You can create
  [test labels](/docs/getting-started/test-labels/) without receiving a charge by using the shipping method Unstamped
  letter (`"id": 8`)
</Tip>

```http Request method, URL, and Authorization header theme={null}
PUT https://panel.sendcloud.sc/api/v2/parcels
Authorization: Basic <base64-encoded-token>
```

```json Example request body theme={null}
{
  "parcel": {
    "id": 1,
    "request_label": true,
    "name": "Mr Test",
    "shipment": {
      "id": 8,
      "name": "Unstamped letter"
    }
  }
}
```

Once you've prepared the response body, make a `PUT` request to the [Update a parcel endpoint](/api/v2/parcels/update-a-parcel). Make sure to include your authentication and content headers, as you did in Step 2.

If everything goes well, you should receive a response similar to the one below:

```json Example response body theme={null}
{
  "parcel": {
    "id": 1,
    "name": "Mr Test",
    "shipment": {
      "id": 8,
      "name": "Unstamped letter"
    },
    "status": {
      "id": 1000,
      "message": "Ready to send"
    },
    "label": {
      "normal_printer": [
        "https://panel.sendcloud.sc/api/v2/labels/normal_printer/1?start_from=0",
        "https://panel.sendcloud.sc/api/v2/labels/normal_printer/1?start_from=1",
        "https://panel.sendcloud.sc/api/v2/labels/normal_printer/1?start_from=2",
        "https://panel.sendcloud.sc/api/v2/labels/normal_printer/1?start_from=3"
      ],
      "label_printer": "https://panel.sendcloud.sc/api/v2/labels/label_printer/1"
    },
    "shipping_method": 8
    // ... other parcel data
  }
}
```

Notice that the response reflects the updates you have made to the customer `name`, and that the parcel `status` is now **"Ready to send"**. The shipping method has been updated to **"Unstamped letter"**.

## Step 4: Download the shipping label

At the end of the previous step, you should have received a response which contains some URLs under the `label` field. These URLs are your links to download the shipping label. Labels can be downloaded in PDF format and are provided in A4 size for normal printers, and A6 size for label printers.

Under `normal_printer`, the `start_from` value indicates the position of the label on an A4 size page:

* `0` = Top left
* `1` = Top right
* `2` = Bottom left
* `3` = Bottom right

You'll need to provide your API credentials again to access the link to download your labels. You can do this by making a `GET` request to the URL of the label you want to access, and including the `Authorization` header.

```http Request method, URL, and Authorization header theme={null}
GET https://panel.sendcloud.sc/api/v2/labels/normal_printer/1?start_from=0
Authorization: Basic <base64-encoded-token>
```

<Tip>
  Labels can also be downloaded in bulk directly from the Sendcloud platform under the **Created labels** tab, or via
  the [Retrieve multiple PDF labels](/api/v2/labels/retrieve-multiple-pdf-labels) and [Bulk PDF label
  printing](/api/v2/labels/bulk-pdf-label-printing) endpoints.
</Tip>

**Congrats!** You've just created your first parcel and downloaded the shipping label via the API.

## Next steps

You can continue reading more tutorials or dive directly into exploring our API references.

* [Choose a shipping method](/docs/shipping/shipping-methods) - learn how to retrieve the full list of shipping services available to you via Sendcloud
* [Tracking parcels](/docs/archive/tracking/tracking-parcels) - to see how you can track the delivery journey of your newly created parcel as it travels to your customer
* [Create a return](/docs/returns/return-portal) - read how you can create a return parcel shipment using the Sendcloud Returns API
* [API v2 reference](/api/v2/) and [API v3 reference](/api/v3/) - browse our API references to explore more options for creating parcels and managing your shipping processes.

## Advanced options

### Create a parcel and immediately request a label in a single API call

If you already know which shipping method you want to use to send your parcel, you can bypass Step 3 above by making a `POST` request to the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint, including `"request_label": "true"`.

<Note>
  When directly announcing parcels in this way, the `shipment` field is mandatory, and a shipping method `id` and `name`
  must be provided in the API request. If you're [shipping parcels
  internationally](/docs/shipping/international-shipping/), pay attention to the additional fields which become
  mandatory for customs documentations purposes. A full list of required parameters can be found in the [API
  reference](/api/v2/parcels/create-a-parcel-or-parcels).
</Note>

### Create a return parcel

You can use the [Create a parcel or parcels](/api/v2/parcels/create-a-parcel-or-parcels) endpoint to create return labels via the API. The process for creating a return label via this method is the same as for creating a parcel, but you must set the value of the `is_return` property to `true` and specify the customer's address address in the `from_*` fields.

It's important to note that standard shipping methods don't apply to return parcels. You can find an overview of available return methods via the [List of all shipping methods](/api/v2/shipping-methods/retrieve-a-list-of-shipping-methods) endpoint and include the parameter `"is_return": true`.

<Info>
  You can also create returns using the **Returns API** by following the [Create a return
  guide](/docs/returns/return-portal/).
</Info>

### Ship parcels and retrieve methods for your sender addresses based in other countries

You can set up multiple sender addresses in your Sendcloud account, and specify which sender address you want to ship from when you create a parcel. See our [sender addresses documentation](/docs/getting-started/sender-addresses) for more info.

### Automatically apply your preferred shipping methods via shipping rules

Shipping rules are a Sendcloud feature which can be used in conjunction with the API to take the legwork out of manually choosing and selecting the best method for your created parcels. See our [shipping rules documentation](/docs/shipping/shipping-rules/) for more details.

### Print your brand logo on your shipping labels

You can customize a brand in your Sendcloud account to make use of handy marketing tools, such as customizable tracking notifications and branded return portals for each of your integrations. See more about creating your brand in our [help center](https://support.sendcloud.com/hc/en-us/articles/360041212392-How-to-set-up-your-brand-).

### Receive real time parcel status updates via Webhooks

There are two ways to receive real-time parcel event notifications:

* **Classic webhooks** — configure webhook URLs directly in the [Sendcloud platform](https://app.sendcloud.com/v2/settings/integrations/manage) or via the [Webhooks API](/api/v3/webhooks/index). This is the established approach for receiving parcel status updates.
* **Event Subscriptions API** — programmatically create [connections and subscriptions](/api/v3/event-subscriptions/index) to control where events are delivered and which events you listen for. Supports webhook endpoints and third-party integrations like Klaviyo.

<Note>The Event Subscriptions API is currently in **BETA**.</Note>


> ## Documentation Index
> Fetch the complete documentation index at: https://sendcloud.dev/llms.txt
> Use this file to discover all available pages before exploring further.

# Returns API overview

The Sendcloud **Returns API** lets you create standalone returns easily and efficiently, so you can seamlessly incorporate returns into your existing workflow, ERP or WMS system. This API can be used in conjunction with other core Sendcloud features or independently.

## What can you do with this API?

* Create a return parcel from national and international destinations
* Retrieve a list of returns created within a specified time period, or with a specific parcel status
* Retrieve return data, including up-to-date tracking information and return reasons per item
* Validate a return before you create the shipping label to avoid unwanted carrier charges
* Request a cancellation for a return parcel

## How does the Returns API differ from the Return portal API?

The [Return portal API](/api/v2/return-portal) is designed to allow you to **build your own custom version** of the Sendcloud Return portal. It requires an outgoing parcel lookup step in order to create a return.

Via the Returns API, you **don't need to have created the original outgoing parcel in Sendcloud** in order to create a return. This makes the Returns API an ideal solution for e-commerce retailers at every scale, even if you don't currently use Sendcloud to ship parcels or process orders.


> ## Documentation Index
> Fetch the complete documentation index at: https://sendcloud.dev/llms.txt
> Use this file to discover all available pages before exploring further.

# Parcel tracking overview

The [Parcel Tracking API](/api/v3/parcel-tracking/retrieve-tracking-information-for-a-parcel) allows you to register and monitor parcels in Sendcloud, even if they were not shipped via Sendcloud. By registering external parcels, you can retrieve their tracking timeline and integrate Sendcloud’s monitoring, analytics, and post-purchase visibility into your own systems.

This API provides two core capabilities:

* Register a parcel for tracking
* Retrieve a complete timeline of tracking events

<Info>
  Note: This guide covers our latest version, Parcel Tracking API v3. For full endpoint and schema documentation, see
  the [API reference](/api/v3/parcel-tracking/retrieve-tracking-information-for-a-parcel).
</Info>

## When to use the Parcel Tracking API

Use the Parcel Tracking API when you want to:

* Display tracking information to customers.
* Monitor externally shipped parcels and/or internal shipments in back-office dashboards.
* Automate post-purchase support workflows.
* Analyze shipping performance, delivery timelines, and trends.

Typical implementation scenarios include:

* Tracking parcels fulfilled outside Sendcloud.
* Consolidating tracking visibility across multiple logistics providers.
* Building custom tracking portals or support tools.

<Warning>
  Note: High-frequency polling is discouraged. Webhook support for tracking external parcels is not yet available.
</Warning>

## How it fits into the Sendcloud workflow

The Parcel Tracking API operates after shipment creation.

Typical flow:

* A parcel is shipped outside Sendcloud.
* You register the parcel via the Parcel Tracking API.
* Sendcloud begins monitoring tracking events.
* You retrieve the tracking timeline via the API.
* Tracking data is integrated into customer-facing portals, internal dashboards, or post-purchase workflows.

Note: Tracking webhooks do not currently fire for parcels created via this API. Webhook support will be added in a future release.

## Key concepts

| Concept                         | Definition                                                                                                                                                                                                                                                                                                 |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Parcel Tracking object**      | Represents a single parcel being tracked in Sendcloud. It is independent of Sendcloud shipments, meaning no shipment or label needs to exist in Sendcloud and no carrier announcement is triggered. This allows externally shipped parcels to be registered and monitored without using the Shipments API. |
| **Tracking Events**             | The Retrieve tracking information endpoint returns a timeline of parcel events. The timeline contains both historical and near-real-time updates. You can determine the parcel’s current status by inspecting the most recent event. The event types that can be shown include:                            |
| **Internal (Sendcloud) events** | Updates generated by Sendcloud for parcels announced via Sendcloud.                                                                                                                                                                                                                                        |
| **Carrier tracking events**     | Status updates received directly from the carrier reflecting the parcel’s physical journey.                                                                                                                                                                                                                |
