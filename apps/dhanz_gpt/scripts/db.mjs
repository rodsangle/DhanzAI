#!/usr/bin/env node
// Database tasks. Usage:
//   node scripts/db.mjs migrate            apply db/migrations/*.sql in order (tracked in schema_migrations)
//   node scripts/db.mjs seed               create the workspace (WORKSPACE_NAME, WORKSPACE_DOMAIN)
//   node scripts/db.mjs seed-demo          demo users + sample chats, LOCAL databases only
//   node scripts/db.mjs stubs              LOCAL ONLY: Supabase auth/storage stand-ins for plain Postgres
//   node scripts/db.mjs platform           self-hosted plain Postgres: the same auth/storage layer (refuses Supabase)
//   node scripts/db.mjs signup-mode MODE   'domain' (workspace email domains) or 'personal' (own workspace each)
// Reads DATABASE_URL (use Supabase's direct or session connection string for migrations).
import fs from "node:fs";
import path from "node:path";
import postgres from "postgres";

const url = process.env.DATABASE_URL_MIGRATIONS || process.env.DATABASE_URL;
if (!url) {
  console.error("Set DATABASE_URL (see .env.example).");
  process.exit(1);
}
const isLocal = /@(localhost|127\.0\.0\.1|\[::1\])[:/]/.test(url);
const sql = postgres(url, { max: 1, onnotice: false });
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const cmd = process.argv[2];

async function migrate() {
  await sql`create table if not exists schema_migrations (name text primary key, applied_at timestamptz not null default now())`;
  const done = new Set((await sql`select name from schema_migrations`).map((r) => r.name));
  const files = fs.readdirSync(path.join(root, "db/migrations")).filter((f) => f.endsWith(".sql")).sort();
  for (const f of files) {
    if (done.has(f)) continue;
    const body = fs.readFileSync(path.join(root, "db/migrations", f), "utf8");
    await sql.begin(async (tx) => {
      await tx.unsafe(body);
      await tx`insert into schema_migrations (name) values (${f})`;
    });
    console.log("applied", f);
  }
  console.log("migrations up to date");
}

async function seed() {
  const name = process.env.WORKSPACE_NAME ?? "RODRECH";
  const domain = process.env.WORKSPACE_DOMAIN ?? "rodrech.com";
  const [ws] = await sql`
    insert into workspaces (name, allowed_email_domain, settings)
    select ${name}, ${domain}, '{"timezone":"America/New_York","public_links_allowed":false}'::jsonb
    where not exists (select 1 from workspaces where allowed_email_domain = ${domain})
    returning id`;
  console.log(ws ? `created workspace ${name} for @${domain}` : `workspace for @${domain} already exists`);

  // Starter team assistants (no author, so admins look after them). Added once each, by name.
  const starters = [
    {
      name: "Copywriter",
      description: "Captions, emails and site copy in the RODRECH voice.",
      instructions:
        "You write marketing copy for RODRECH, a streetwear brand built around headwear.\n" +
        "Voice: confident and quiet. Short lines. Plain words. No exclamation marks, no hype words (\"epic\", \"insane\", \"must-have\").\n" +
        "Lead with the product and one concrete detail (fabric, fit, colourway). Offer three options unless asked for one.\n" +
        "If a detail like a price, date or quantity isn't given, leave a clear placeholder like [PRICE] rather than inventing it.",
      starters: ["Three Instagram captions for a new fitted drop", "A launch email for Friday's restock", "Rewrite this product page to sound like us"],
    },
    {
      name: "Product description writer",
      description: "Product page copy and spec bullets from a tech pack or notes.",
      instructions:
        "You turn product notes and tech packs into product page copy for RODRECH headwear.\n" +
        "Output: a 2–3 sentence description, then bullets for materials, fit, closure, care and origin.\n" +
        "Use only facts from the notes or attached files. Mark anything missing as [NEEDED: …] instead of guessing.",
      starters: ["Write the product page for this cap", "Turn this tech pack into spec bullets", "Shorten this description for mobile"],
    },
    {
      name: "Campaign planner",
      description: "Drop calendars, shot lists and launch checklists.",
      instructions:
        "You plan product drops and campaigns for RODRECH.\n" +
        "Work backwards from the launch date. Give dated checklists with an owner role per task (design, production, content, ecommerce).\n" +
        "Flag risks early: sampling and production lead times, shipping cut-offs, asset deadlines.",
      starters: ["Plan a 4-week run-up to a fitted drop", "A shot list for a lookbook", "What could go wrong with a Friday launch?"],
    },
  ];
  for (const a of starters) {
    const rows = await sql`
      insert into assistants (workspace_id, owner_id, name, description, instructions, starters, capabilities, visibility)
      select w.id, null, ${a.name}, ${a.description}, ${a.instructions}, ${a.starters}, '{web_search,image_generation}', 'workspace'
      from workspaces w where w.allowed_email_domain = ${domain}
        and not exists (select 1 from assistants x where x.workspace_id = w.id and x.name = ${a.name})
      returning id`;
    if (rows.length) console.log(`added starter assistant ${a.name}`);
  }
}

async function seedDemo() {
  if (!isLocal && !process.argv.includes("--force")) {
    console.error("seed-demo inserts fake users into auth.users. It only runs against a local database (or pass --force).");
    process.exit(1);
  }
  await seed();
  const users = [
    { email: "dante@rodrech.com", name: "Dante" },
    { email: "maya@rodrech.com", name: "Maya Lee" },
  ];
  const ids = {};
  for (const u of users) {
    const [row] = await sql`
      insert into auth.users (email, raw_user_meta_data) values (${u.email}, ${sql.json({ full_name: u.name })})
      on conflict (email) do update set email = excluded.email returning id`;
    ids[u.email] = row.id;
  }
  const dante = ids["dante@rodrech.com"], maya = ids["maya@rodrech.com"];
  const [{ id: W }] = await sql`select workspace_id as id from memberships where user_id = ${dante}`;
  const already = await sql`select 1 from projects where workspace_id = ${W} limit 1`;
  if (already.length) return console.log("demo content already present");

  const [fw26] = await sql`insert into projects (workspace_id, owner_id, name, instructions, created_at, updated_at) values (
    ${W}, ${dante}, 'FW26 drop',
    'Brand voice for RODRECH: confident, streetwise, never corny. Write captions in lowercase. Short sentences. No emojis unless asked. The FW26 collection is headwear-led: snapbacks, fitted caps and beanies in black, bone and olive.',
    now() - interval '6 days', now() - interval '30 minutes') returning id`;
  const [tags] = await sql`insert into projects (workspace_id, owner_id, name, instructions, created_at, updated_at) values (
    ${W}, ${dante}, 'Hang tags & packaging',
    'Hang tag copy must fit a 2-inch card: one headline under 6 words, one line under 12 words.',
    now() - interval '3 days', now() - interval '5 hours') returning id`;
  await sql`insert into project_members (project_id, user_id, role) values (${fw26.id}, ${maya}, 'editor')`;

  const convo = async (title, minsAgo, projectId, q, a, owner = dante) => {
    const [c] = await sql`insert into conversations (workspace_id, user_id, project_id, title, model, last_message_at, created_at)
      values (${W}, ${owner}, ${projectId}, ${title}, 'claude-sonnet-5-5', now() - make_interval(mins => ${minsAgo}), now() - make_interval(mins => ${minsAgo + 5})) returning id`;
    const [u] = await sql`insert into messages (conversation_id, user_id, role, content, text, created_at)
      values (${c.id}, ${owner}, 'user', ${sql.json([{ type: "text", text: q }])}, ${q}, now() - make_interval(mins => ${minsAgo + 2})) returning id`;
    const [r] = await sql`insert into messages (conversation_id, parent_id, role, content, text, model, created_at)
      values (${c.id}, ${u.id}, 'assistant', ${sql.json([{ type: "text", text: a }])}, ${a}, 'claude-sonnet-5-5', now() - make_interval(mins => ${minsAgo})) returning id`;
    await sql`update conversations set current_leaf_id = ${r.id} where id = ${c.id}`;
  };
  await convo("Hang tag copy, round 3", 25, tags.id, "Give me hang tag options for the olive beanie.",
    "Three options that fit a 2-inch card:\n\n1. **Cold-proof crown.**  \n   Ribbed olive knit, built for long nights out.\n2. **Olive, on purpose.**  \n   Heavyweight rib. Folds up, never down.\n3. **Head start.**  \n   The FW26 beanie, cut deep for a clean fold.\n\nOption 2 reads strongest on a small card.");
  await convo("Snapback caption options for Instagram stories and reels", 90, fw26.id, "Captions for the black snapback drop, Friday noon.",
    "- built for the block. fw26 snapbacks, friday 12pm.\n- black on black. no notes. friday.\n- the crown you've been waiting on drops friday at noon.\n\nWant shorter versions for stories?");
  await convo("Lookbook shot list", 60 * 26, fw26.id, "Draft a shot list for the FW26 lookbook, one location, 12 looks.",
    "## Shot list: FW26 lookbook\n\n| # | Look | Shot | Notes |\n| --- | --- | --- | --- |\n| 1 | Black snapback + bone tee | Full body, straight on | Hero shot |\n| 2 | Olive beanie + black hoodie | Waist up, 3/4 | Fold visible |\n| 3 | Bone fitted | Tight on logo | Shallow focus |\n\nI can fill in looks 4 to 12 once the rack is final.");
  await convo("Shopify product descriptions", 60 * 50, null, "Write a Shopify description for the bone fitted cap.",
    "**RODRECH Bone Fitted**\n\nStructured six-panel crown in a warm bone twill, with a flat brim and tonal embroidery. Fitted sizing, so check the size chart before you order.\n\n- 100% cotton twill\n- Sweatband lined for all-day wear\n- Spot clean only");
  await convo("Influencer outreach email", 60 * 24 * 5, null, "Short outreach email to a skate creator about the FW26 drop.",
    "Subject: FW26 caps for your next session\n\nHey Jordan,\n\nWe've been watching your edits and the style lines up with what we're dropping in FW26. We'd like to send you a few caps before launch, no strings. If they end up in a video, great.\n\nWhat's the best address to ship to?\n\nDante, RODRECH");
  await convo("Drop day checklist", 60 * 30, fw26.id, "What should Maya check on drop day?",
    "1. Inventory synced in Shopify by 10am\n2. Product pages live but hidden\n3. Email scheduled for 11:55\n4. Stories queued\n5. Support macros ready for sizing questions", maya);
  await sql`insert into personalization (user_id, about_you, response_style) values (${dante},
    'I run creative and marketing for RODRECH, a streetwear brand focused on headwear.', 'Direct. Give options, not essays.')
    on conflict (user_id) do nothing`;
  console.log("demo users and content created");
}

async function stubs() {
  if (!isLocal) {
    console.error("stubs only runs against a local database.");
    process.exit(1);
  }
  await sql.unsafe(fs.readFileSync(path.join(root, "db/test/supabase-stubs.sql"), "utf8"));
  console.log("local Supabase stand-ins installed");
}

async function platform() {
  const [{ supa }] = await sql`
    select exists (select 1 from pg_roles where rolname in ('supabase_admin', 'supabase_auth_admin'))
        or exists (select 1 from information_schema.tables where table_schema = 'auth' and table_name = 'identities') as supa`;
  if (supa) {
    console.error("This looks like a Supabase database: it already has its own auth and storage. Nothing done.");
    process.exit(1);
  }
  await sql.unsafe(fs.readFileSync(path.join(root, "db/platform/plain-postgres.sql"), "utf8"));
  console.log("plain-Postgres auth/storage layer in place");
}

async function signupMode(mode) {
  if (mode !== "domain" && mode !== "personal") {
    console.error("usage: node scripts/db.mjs signup-mode domain|personal");
    process.exit(1);
  }
  await sql`update platform_settings set value = ${mode}, updated_at = now() where key = 'signup_mode'`;
  console.log("sign-up mode:", mode);
}

try {
  if (cmd === "migrate") await migrate();
  else if (cmd === "seed") await seed();
  else if (cmd === "seed-demo") await seedDemo();
  else if (cmd === "stubs") await stubs();
  else if (cmd === "platform") await platform();
  else if (cmd === "signup-mode") await signupMode(process.argv[3]);
  else {
    console.error("usage: node scripts/db.mjs migrate|seed|seed-demo|stubs|platform|signup-mode");
    process.exitCode = 1;
  }
} catch (e) {
  console.error(e.message);
  process.exitCode = 1;
} finally {
  await sql.end();
}
