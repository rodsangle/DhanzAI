import "server-only";
import crypto from "node:crypto";
import { AppError, call, str, testBase, type AppProvider } from "./types";

/**
 * Shopify through the Admin GraphQL API, installed on your store with OAuth (authorization
 * code grant; the callback's HMAC is checked with the app secret). Scopes: read_products,
 * write_products. productUpdate takes `product: ProductUpdateInput` (API 2024-10 and later).
 */
const VERSION = () => process.env.SHOPIFY_API_VERSION || "2026-10";
export const SHOP_RE = /^[a-z0-9][a-z0-9-]{0,60}\.myshopify\.com$/;
const origin = (shop: string) => {
  if (!SHOP_RE.test(shop)) throw new AppError("That isn't a .myshopify.com store address.", 400);
  const t = testBase();
  return t ? `${t}/shop` : `https://${shop}`;
};

/** Shopify signs the callback's query string; anything else is refused. */
export function verifyShopifyHmac(query: URLSearchParams) {
  const hmac = query.get("hmac") ?? "";
  const msg = [...query.entries()].filter(([k]) => k !== "hmac" && k !== "signature").sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([k, v]) => `${k}=${v}`).join("&");
  const want = crypto.createHmac("sha256", process.env.SHOPIFY_CLIENT_SECRET ?? "").update(msg).digest("hex");
  return hmac.length === want.length && crypto.timingSafeEqual(Buffer.from(hmac), Buffer.from(want));
}

async function gql(shop: string, token: string, query: string, variables: Record<string, unknown>) {
  const res = await call(`${origin(shop)}/admin/api/${VERSION()}/graphql.json`, {
    what: "Shopify", method: "POST", headers: { "X-Shopify-Access-Token": token, "Content-Type": "application/json" }, body: JSON.stringify({ query, variables }),
  });
  const j = (await res.json()) as { data?: Record<string, unknown>; errors?: { message: string }[] };
  if (j.errors?.length) throw new AppError(`Shopify returned an error: ${j.errors[0].message}`);
  return j.data ?? {};
}

const gid = (id: string) => (id.startsWith("gid://shopify/Product/") ? id : /^\d+$/.test(id) ? `gid://shopify/Product/${id}` : null);

export const shopifyApp: AppProvider = {
  id: "shopify",
  name: "Shopify",
  mentions: ["Shopify"],
  description: "Look up products in your store and update product descriptions.",
  can: ["Search products", "Update a product description (asks first)"],
  needsShop: true,
  configured: () => !!(process.env.SHOPIFY_CLIENT_ID && process.env.SHOPIFY_CLIENT_SECRET),
  authorizeUrl: ({ state, redirectUri, shop }) =>
    `${origin(shop!)}/admin/oauth/authorize?${new URLSearchParams({ client_id: process.env.SHOPIFY_CLIENT_ID!, scope: "read_products,write_products", redirect_uri: redirectUri, state })}`,
  async exchange({ code, shop, query }) {
    if (!verifyShopifyHmac(query)) throw new AppError("Shopify's reply couldn't be verified. Try connecting again.", 400);
    if (query.get("shop") !== shop) throw new AppError("That reply came from a different store.", 400);
    const res = await call(`${origin(shop!)}/admin/oauth/access_token`, {
      what: "Shopify", method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: process.env.SHOPIFY_CLIENT_ID, client_secret: process.env.SHOPIFY_CLIENT_SECRET, code }),
    });
    const j = (await res.json()) as { access_token: string; scope: string };
    return { tokens: { access_token: j.access_token, scopes: j.scope.split(",") }, account: { id: shop!, label: shop! } };
  },
  tools: [
    {
      name: "shopify_search_products",
      description: "Search products in the Shopify store by title or other Shopify product search terms. Returns up to 10 with id, title, status, inventory and description.",
      input_schema: { type: "object", properties: { query: { type: "string" } }, required: ["query"] },
      importance: "read",
      describe: (i) => `Searched Shopify products for “${str(i.query, 80)}”`,
      preview: (i) => [{ label: "Search for", value: str(i.query, 200) }],
      async run({ token, shop }, i) {
        const d = (await gql(shop!, token, `query($q: String!) { products(first: 10, query: $q) { nodes { id title handle status totalInventory descriptionHtml } } }`, { q: str(i.query, 200) })) as {
          products: { nodes: { id: string; title: string; descriptionHtml: string }[] };
        };
        const nodes = d.products.nodes.map((n) => ({ ...n, descriptionHtml: n.descriptionHtml.slice(0, 1500) }));
        return { result: JSON.stringify(nodes), summary: `${nodes.length} products found` };
      },
    },
    {
      name: "shopify_update_product_description",
      description: "Replace a product's description on the live store. Only when the person asked for it. description_html is simple HTML (<p>, <ul>, <li>, <strong>).",
      input_schema: { type: "object", properties: { product_id: { type: "string" }, product_title: { type: "string" }, description_html: { type: "string" } }, required: ["product_id", "description_html"] },
      importance: "important",
      describe: (i) => `Updated the description of ${str(i.product_title, 80) || "a product"} on Shopify`,
      preview: (i) => [
        { label: "Product", value: str(i.product_title, 200) || str(i.product_id, 100) },
        { label: "New description", value: str(i.description_html, 2000) },
      ],
      async run({ token, shop }, i) {
        const id = gid(str(i.product_id, 100));
        if (!id) throw new AppError("That isn't a Shopify product id.", 400);
        const d = (await gql(shop!, token, `mutation($product: ProductUpdateInput!) { productUpdate(product: $product) { product { id title } userErrors { field message } } }`, {
          product: { id, descriptionHtml: str(i.description_html, 20_000) },
        })) as { productUpdate: { product: { id: string; title: string } | null; userErrors: { message: string }[] } };
        if (d.productUpdate.userErrors.length) throw new AppError(`Shopify didn't save it: ${d.productUpdate.userErrors[0].message}`, 400);
        return { result: JSON.stringify(d.productUpdate.product), summary: `Updated ${d.productUpdate.product?.title}` };
      },
    },
  ],
};
