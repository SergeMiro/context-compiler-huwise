# Huwise: what is publicly documented (source file)

All checks were made on **2026-11-11** (the "Checked" column says the same on every row, so each row stands alone when copied).
Huwise was formerly Opendatasoft. Some official docs still live on `help.opendatasoft.com`, and the API docs still use the name "Opendatasoft Query Language (ODSQL)".

How the pages were read: `curl` GET (static HTML, JSON) plus the BrowserOS Neo browser on this VPS (rendering data.education.gouv.fr). The only MCP traffic was `initialize` requests sent without credentials. All of them were rejected (401), and no tool was ever called.
browser: local (Neo) + fetch (curl)

Status tags:
- **VERIFIED**: a verbatim quote on an official page supports the claim.
- **INFERRED**: plausible from what was observed (page source, config, a live API response), but no documentation states it.
- **UNKNOWN**: not public.

---

## 0. Pages checked

| # | Requested URL | Final URL / result |
|---|---|---|
| P1 | https://www.huwise.com/en/living-context-layer/ | 200, same URL |
| P2 | https://mcp.huwise.com/docs | 200. A Swagger UI shell. Its content comes from https://mcp.huwise.com/openapi.json (200, OpenAPI 3.1, `info.version` 2.1.0) |
| P3 | https://www.huwise.com/en/blog/huwise-mcp-agentic-ai/ | 200, same URL (Lauréline Saux, 06 Oct 2026) |
| P4 | https://userguide.huwise.com/ | 200 (a Front knowledge base, home page in French). The English articles are under https://userguide.huwise.com/en/articles/... The site search is rendered by JavaScript, so the articles were found by crawling the categories (39 categories, 306 articles) |
| P5 | https://data.education.gouv.fr/ | 302 → https://data.education.gouv.fr/pages/accueil/ (200) |
| P6 | Explore API v2.1 docs | `https://data.education.gouv.fr/api/explore/v2.1/documentation` → 302 to `help.huwise.com/apis/ods-explore-v2/explore_v2.1.html` → 301 to **https://help.opendatasoft.com/apis/ods-explore-v2/explore_v2.1.html** (200). The portal's own spec is https://data.education.gouv.fr/api/explore/v2.1/swagger.json (200). The console `/api/explore/v2.1/console` → https://data.education.gouv.fr/api-console/explore/v2.1/ (200) |

Extra official pages that were read:

| # | URL |
|---|---|
| X1 | https://userguide.huwise.com/en/articles/5071874 ("Using Huwise's MCP server", edited 16 Sep 2026) |
| X2 | https://userguide.huwise.com/en/articles/6504002 ("Huwy, your AI exploration assistant", edited 3 Jun 2026) |
| X3 | https://userguide.huwise.com/en/articles/9811266 ("Configure your Huwy assistant") |
| X4 | https://userguide.huwise.com/en/articles/9847810 (Huwy quota for users) |
| X5 | https://www.huwise.com/en/mcp-ai-agents/ |
| X6 | https://www.huwise.com/en/blog/huwy-ai-agent-for-smart-data-exploration/ (09 Dec 2025) |
| X7 | https://www.huwise.com/en/blog/huwise-agentic-framework-data-marketplaces/ (15 Sep 2026) |
| X8 | https://data.education.gouv.fr/pages/connecter-une-ia/ |
| X9 | https://userguide.huwise.com/en/articles/2040578 ("Analyzing actions") |
| X10 | https://userguide.huwise.com/en/articles/10271554 (dataset Analytics tab) |
| X11 | https://userguide.huwise.com/en/articles/10271490 (conversion funnel) |
| X12 | https://userguide.huwise.com/en/articles/2042562 ("Managing tracking") |
| X13 | https://userguide.huwise.com/en/articles/2041602 ("Managing permissions", edited 5 Nov 2026) |
| X14 | https://userguide.huwise.com/en/articles/2043458 ("A dataset's Security tab") |
| X15 | https://userguide.huwise.com/en/articles/2044226 ("Managing API keys") |
| X16 | https://userguide.huwise.com/en/articles/2257410 ("An introduction to the Explore API") |
| X17 | https://userguide.huwise.com/en/articles/2730498 ("How to use the Explore data with AI feature") |
| X18 | https://www.huwise.com/en/integration-connectivity/ |
| X19 | https://www.huwise.com/en/api-export/ |
| X20 | https://www.huwise.com/en/user-access-management/ |
| X21 | https://www.huwise.com/en/analytics-conversion/ |
| X22 | https://www.huwise.com/en/data-catalog-solution/ |
| X23 | https://userguide.huwise.com/en/articles/2257730 ("How to search your data with AI (vector search)") |

Pages that failed or gave nothing useful:
- `https://mcp.huwise.com/docs` contains no content itself (it is a JS Swagger shell). Everything was read from `/openapi.json`.
- The site search on `userguide.huwise.com/en/search?q=...` is client-side only: curl returns no results. The Front KB `/api/v2/help_center/...` endpoint does not exist (non-JSON response).
- `https://static.huwise.com/agents/` → 404. `https://agents-chat-api.huwise.com/health` → 404 (the documented health path is `/api/health`, see H).
- `https://semantics-chat.wikit.ai/chat-embed.js` (loaded by the data.education.gouv.fr page) → 504 when fetched with curl.
- `https://mcp.huwise.com/.well-known/oauth-protected-resource` → 404 (no OAuth discovery found).
- The WebSearch `site:userguide.huwise.com Huwy` returned only Huawei pages. It was not used.

---

## A. External Data Sources

| Claim | Quote (verbatim) | URL | Checked | Status |
|---|---|---|---|---|
| ~80 connectors pull data from business systems, IoT, partners and others | "Thanks to our 80 connectors, you can quickly bring together all your data, whether generated by business systems, IoT sensors, customers, partners or the public on your data portal." | X18 | 2026-11-11 | VERIFIED |
| Connector families include data lakes/warehouses and catalog/virtualization | "Data lakes and data warehouses" / "Data catalog and virtualization" (connector category labels) | X18 | 2026-11-11 | VERIFIED |
| Huwy can explore data virtualized from Snowflake or Databricks without duplicating it | "whether stored in the marketplace or virtualized from tools like Snowflake or Databricks, without needing to duplicate it." | X6 | 2026-11-11 | VERIFIED |
| Harvesters exist for other portals (CKAN, ArcGIS, Huwise Federation) | "Harvest another Huwise workspace to create federated datasets automatically." | https://userguide.huwise.com/en/articles/2022658 | 2026-11-11 | VERIFIED |
| Which sources feed data.education.gouv.fr | Not stated on the portal pages that were read | P5 | 2026-11-11 | UNKNOWN |

## B. Ingestion & Publication

| Claim | Quote (verbatim) | URL | Checked | Status |
|---|---|---|---|---|
| Import previews source data while a dataset is created | "our platform simultaneously imports and previews your source data, saving you time when creating a dataset" | X18 | 2026-11-11 | VERIFIED |
| Processors transform data during ingestion (dozens are documented, e.g. geocoding, JSON expand) | "The Expand JSON array processor transposes rows containing a JSON array into several rows" | https://userguide.huwise.com/en/articles/2033090 | 2026-11-11 | VERIFIED |
| Each published dataset gets its own API automatically | "The Huwise solution automatically generates a structured API for each dataset on your marketplace, complete with an exploration console and reference documentation." | X19 | 2026-11-11 | VERIFIED |
| Analytics count only published datasets | "In this dashboard, we take into account only published datasets." | https://userguide.huwise.com/en/articles/2040834 | 2026-11-11 | VERIFIED |
| Internal pipeline (queues, storage engine, indexing) | Not documented | — | 2026-11-11 | UNKNOWN |

## C. Data Marketplace / Asset Catalog

| Claim | Quote (verbatim) | URL | Checked | Status |
|---|---|---|---|---|
| The marketplace is where business teams and AI agents find and consume data | "the data marketplace is where business teams and AI agents come to find and consume data." | P1 | 2026-11-11 | VERIFIED |
| Asset types go beyond datasets | "searching and analyzing assets (datasets, visualizations, showcases, pages, reuses)" | X1 | 2026-11-11 | VERIFIED |
| AI (vector) search ranks by semantic similarity | "find results by calculating the semantic similarity between the query and the data assets on your domain." | X23 | 2026-11-11 | VERIFIED |
| data.education.gouv.fr catalog size, seen in the UI | UI text "1-20/370 résultats" (facets: "Données 285", "Visualisations 85") | https://data.education.gouv.fr/explore/ | 2026-11-11 | VERIFIED (observed UI, not a doc) |
| data.education.gouv.fr dataset count from the API | live response `{"total_count": 314, ...}` from `GET /api/explore/v2.1/catalog/datasets?limit=1&select=dataset_id` | P5 API | 2026-11-11 | VERIFIED (live API). Why 314 differs from 285: UNKNOWN |
| Catalog search ranking / boosting algorithm | Not documented. The page config shows `CATALOG_SEARCH_BOOSTING_ENABLED: false` on data.education.gouv.fr | P5 source | 2026-11-11 | UNKNOWN / INFERRED (flag only) |

## D. Living Context Layer (usage signals)

The usage signals named on official pages, quoted exactly. **No page mentions "feedback" as a context-layer signal.** "Unsuccessful searches" is named once (P1). Dataset feedback exists only as a deprecated legacy feature (see last row).

| Claim | Quote (verbatim) | URL | Checked | Status |
|---|---|---|---|---|
| The context layer combines the supply side (data knowledge) and the demand side (usage) | "On the supply side, it draws on knowledge about the data: the assets, schemas, definitions, and lineage of each data product." | P1 | 2026-11-11 | VERIFIED |
| Demand-side signals: searches, views, exports, access requests, drop-off points, user journeys | "it captures usage signals: searches, views, exports, access requests, drop-off points, and user journeys specific to each user profile." | P1 | 2026-11-11 | VERIFIED |
| Unsuccessful searches and corrections also count | "Every search, export, access request, or correction enriches the context, including unsuccessful searches." | P1 | 2026-11-11 | VERIFIED |
| Governance rules applied at the point of use are recorded | "Governance rules applied at the point of use are also recorded." | P1 | 2026-11-11 | VERIFIED |
| Questions are also a demand signal | "every search, question, or access request highlights users’ tangible data needs." | P1 | 2026-11-11 | VERIFIED |
| Usage knowledge comes from the conversion funnel, built-in analytics and lineage | "Draws on marketplace usage signals (searches, drop-off points in the user journey, views, or consumption actions) collected through the conversion funnel, built-in analytics, and data lineage" | X7 | 2026-11-11 | VERIFIED |
| Other context components: semantics, business rules, user knowledge (SSO attributes) | "Relies on information such as users’ roles, profiles, statuses, or certain attributes retrieved through SSO" | X7 | 2026-11-11 | VERIFIED |
| The MCP server measures agent usage | "Every action an agent performs on Huwise passes through the MCP server, which allows it to be measured." | P3 | 2026-11-11 | VERIFIED |
| The MCP server shares part of the context layer with agents | "The MCP server shares some of this knowledge with agents, which they can then leverage directly." | P3 | 2026-11-11 | VERIFIED |
| Access channels are tracked (marketplace, APIs, AI environments) | "precisely identifying access channels — data marketplace, APIs, AI environments — to optimize data distribution" | X5 | 2026-11-11 | VERIFIED |
| Built-in analytics: text searches with the number of results per term (the documented basis for spotting zero-result searches) | "sort the data not only based on the number of times that term has been used, but also the number of results obtained using each term." | X9 | 2026-11-11 | VERIFIED |
| Funnel metrics: impressions → overview click (CTR) → main consumption tool (FCR) | "how many people saw your asset in search results, how many clicked through, and how many of those visitors went on to use its main consumption tool" | X10 | 2026-11-11 | VERIFIED |
| Dataset Activity tab: users, downloads, API calls and where they came from | "how many users interacted with your dataset, how many times it was downloaded, and how many API calls were made against it" | X10 | 2026-11-11 | VERIFIED |
| Native monitoring focuses on API calls | "The monitoring tools provided by Huwise focus on API calls and usages." | X12 | 2026-11-11 | VERIFIED |
| Turnkey agents consume these signals (Marketplace Curator, Opportunity Spotter, Data Product Builder/Designer, Metadata Filler) | "Marketplace Curator: an agent that continuously analyzes data marketplace usage (clicks, consumption, drop-offs, etc.)" | X7 | 2026-11-11 | VERIFIED |
| A "usage matrix" interprets the signals | "represented through a usage matrix that structures and interprets the main signals generated by marketplace usage." | X7 | 2026-11-11 | VERIFIED (that it exists). Contents: UNKNOWN |
| data.education.gouv.fr sends front-end events to a tracking endpoint | page config `tracking: {"enabled": true, "service_url": "/rw/vaf/events", ...}` | P5 / X8 page source | 2026-11-11 | INFERRED (observed config; what it collects is not documented) |
| Dataset "feedback" is a deprecated legacy feature, not named as a context signal | "This feature has been deprecated. We are committed to support it but it will no longer benefit from any upgrade." | https://userguide.huwise.com/en/articles/2039042 | 2026-11-11 | VERIFIED (deprecation). Use as a context signal: UNKNOWN |
| How signals are weighted, stored or ranked | Not documented | — | 2026-11-11 | UNKNOWN |

## E. Governance & Security

| Claim | Quote (verbatim) | URL | Checked | Status |
|---|---|---|---|---|
| Access rules apply to every request, agents included. Tenant context is isolated | "corporate access rules are enforced on every request, including those made by AI agents. Everyone sees only what their permissions allow, while each customer’s context remains strictly isolated." | P1 | 2026-11-11 | VERIFIED |
| Agents act with the identified user's permissions | "As AI agents act on behalf of an identified human user, they are subject to that user’s permissions" | P3 | 2026-11-11 | VERIFIED |
| MCP access is tracked as a usage channel | "Access to data via the MCP is also tracked in the data marketplace to understand its impact as a usage channel." | P3 | 2026-11-11 | VERIFIED |
| Huwy has no special permissions | "No. Huwy respects the same access rules as the platform. Answers depend on what the user is allowed to see." | X2 | 2026-11-11 | VERIFIED |
| Field- and record-level filters per dataset, plus per-user API call limits | "You can apply a filter to control what fields in a dataset are visible in the portal. You can also limit the number of API calls" | X14 | 2026-11-11 | VERIFIED |
| Row filters use the dataset query language | "You can also use the same query language used to search within a dataset to limit which records (or rows) are visible." | X14 | 2026-11-11 | VERIFIED |
| Groups, MFA, SSO with group mapping | "Our solution natively includes advanced security features such as fully configurable multi-factor authentication (MFA) and Single Sign-On (SSO)." | X20 | 2026-11-11 | VERIFIED |
| A "Use Huwy agent" permission exists | "The user may access and use the Huwy agent. This permission only applies when the agent visibility mode is set to \"Restricted\"." | X13 | 2026-11-11 | VERIFIED |
| API keys belong to one workspace and act as the user | "API keys are bound to a specific workspace; they only work on the workspace on which they were created." | X15 | 2026-11-11 | VERIFIED |
| An API key carries the creating user's rights | "By default, every API key authenticates requests as coming from your user, which means they grant the same rights (yours) to any person using them." | P6 | 2026-11-11 | VERIFIED |
| Huwy does not train on portal data | "Huwy explicitly does not use a portal's data to train itself nor the AI model you select to drive the feature." | X2 | 2026-11-11 | VERIFIED |
| Certifications, hosting region, encryption details | Not read in this pass (a /en/security/ page exists but was not fetched) | https://www.huwise.com/en/security/ | 2026-11-11 | UNKNOWN (not checked) |

## F. Explore API / Query layer (ODSQL)

| Claim | Quote (verbatim) | URL | Checked | Status |
|---|---|---|---|---|
| REST, GET only, JSON | "Only the HTTP GET method is supported." / "All API endpoints return JSON." | P6 | 2026-11-11 | VERIFIED |
| Base path per domain | "URL paths start with /api/explore/v2.1 . A path to a resource looks like this: https://<domain>/api/explore/v2.1/<resource> ." | P6 | 2026-11-11 | VERIFIED |
| Records endpoint | `GET /catalog/datasets/{dataset_id}/records`, summary "Query dataset records" | data.education.gouv.fr swagger.json | 2026-11-11 | VERIFIED |
| ODSQL clauses | "The ODSQL is split into five different kinds of clauses:" (select, where, group by, order by and limit) | P6 | 2026-11-11 | VERIFIED |
| What ODSQL is for | "makes it possible to express complex queries as a filtering context for datasets or records and build aggregations or computed fields." | P6 | 2026-11-11 | VERIFIED |
| `limit` max 100 without group_by. offset+limit < 10000 | "For a query **without** a `group_by`: - the maximum value for `limit` is 100, - `offset+limit` should be less than 10000" | swagger.json `limit` param | 2026-11-11 | VERIFIED. Live check: `limit=101` → 400 "-1 <= limit <= 100 is expected" |
| With group_by: limit up to 20000 | "For a query **with** a `group_by`: - the maximum value for `limit` is 20000, - `offset+limit` should be less than 20000" | swagger.json | 2026-11-11 | VERIFIED |
| Records response carries `total_count` and `results` | schema `records`: properties `total_count` (integer), `_links`, `results` | swagger.json | 2026-11-11 | VERIFIED. Live: `select=count(*) as n` on `fr-en-annuaire-education` → `{"total_count": 68557, "results": [{"n": 68557}]}` |
| Exports have no record limit | "While the records endpoint is subject to a limited number of returned records, the exports endpoint has no limitations." | P6 | 2026-11-11 | VERIFIED |
| Export endpoints | `GET /catalog/datasets/{dataset_id}/exports`, `/exports/{format}`, `/exports/csv`, `/exports/parquet`, `/exports/gpx`. Catalog: `/catalog/exports/{format}`, `/catalog/exports/dcat{dcat_ap_format}` | swagger.json | 2026-11-11 | VERIFIED |
| Export `limit` default -1 = all | "Use -1 (default) to retrieve all records" | swagger.json `limit_export` | 2026-11-11 | VERIFIED |
| Other endpoints: facets, attachments, single record, catalog facets | `/catalog/facets`, `/catalog/datasets/{id}/facets`, `/attachments`, `/records/{record_id}` | swagger.json | 2026-11-11 | VERIFIED |
| Auth via the Authorization header or the `apikey` query param. Anonymous access on public portals | "Authorization: Apikey <API_KEY>" / "You'll get data from a portal providing public access to data. So, you don't need an account or an API key." | P6 | 2026-11-11 | VERIFIED. Live: anonymous calls to data.education.gouv.fr succeed |
| v2.1 is stable | "The v2.1 version is stable and production ready: no breaking change will be introduced in the future" | P6 | 2026-11-11 | VERIFIED |
| User-guide wording on records vs export | "API calls are limited to 100 records per call. But if you need to handle all of the data at once, you are able to export the entirety of the data." | X16 | 2026-11-11 | VERIFIED |

## G. Huwise MCP Server

**Endpoint:** `POST https://mcp.huwise.com/mcp`, StreamableHTTP, **stateless**. Server info: "Huwise MCP server", OpenAPI `info.version` 2.1.0. `GET /health` → `{"status":"ok"}` (live).

| Claim | Quote (verbatim) | URL | Checked | Status |
|---|---|---|---|---|
| Transport | "Point any MCP-compatible client to the `/mcp` endpoint (StreamableHTTP, stateless)." | P2 (openapi.json) | 2026-11-11 | VERIFIED |
| Auth: portal + API key, or portal + token | "Portal API key \| `X-Domain: https://your-portal.com` · `X-Apikey: <apikey>`" and "Portal token \| `X-Domain: ...` · `X-Token: <token>`" | P2 | 2026-11-11 | VERIFIED |
| The portal is selected with `X-Domain` (query `?x-domain=` is the fallback) | "Portal domain URL — required for platform auth; falls back to query param when header is absent" | P2 | 2026-11-11 | VERIFIED |
| Tool versions | "`X-Option-Version: beta` \| `?version=beta` \| Use the beta tool set" / "`X-Option-Version: old` ... Use the retired (pre-2.0) tool set". Default `latest` | P2 | 2026-11-11 | VERIFIED |
| Hide the `url` tool parameter | "`X-Option-Disable-Url-Parameter: true` ... Portal URL is read from `X-Domain`; tools won't ask for a URL" | P2 | 2026-11-11 | VERIFIED |
| Plain-HTTP mirror of the tools | "Every `latest`/`beta` tool is also reachable as a standard `GET /tools/{version}/{tool_name}` request" | P2 | 2026-11-11 | VERIFIED |
| Exactly four tools in `latest` | "The Huwise MCP server provides four tools for searching and analyzing your portal's assets, using the Explore API and ODSQL" | X1 | 2026-11-11 | VERIFIED |
| Renamed in v2.0 | "explore_get_datasets , explore_get_dataset and explore_get_dataset_records are now search_assets , get_asset and search_asset_records respectively" | X1 | 2026-11-11 | VERIFIED |
| Not included in every plan | "MCP server functionality is not automatically included in your plan." | X1 | 2026-11-11 | VERIFIED |
| Released July 2025. Tools reorganized "this summer" (2026) into one tool per task | "Our MCP server was released in July 2025." / "Now, each one corresponds to a specific task and returns only the essentials." | P3 | 2026-11-11 | VERIFIED |
| Built on the public APIs | "It relies on our robust, well-documented APIs and makes them usable by AI agents." | P3 | 2026-11-11 | VERIFIED |
| Context includes facets/filters before querying | "It now transmits aggregated information, such as filters and facets, which show the main values of a dataset and their distribution." | P3 | 2026-11-11 | VERIFIED |
| Tested clients | "proven compatibility with major AI environments — Claude Desktop, OpenAI, Mistral AI, Microsoft Copilot" | X5 | 2026-11-11 | VERIFIED |
| ChatGPT / Mistral connectors are not yet available | "We're working on making the Huwise MCP server available as a connector in ChatGPT and Mistral AI, but these connectors are not yet available." | X1 | 2026-11-11 | VERIFIED |

### G.1 Tool set `latest` (from https://mcp.huwise.com/openapi.json, paths `/tools/latest/*`. `beta` has the same 4 names and parameters)

All four take an optional `url` (default `https://data.huwise.com`, "URL of the  catalog"), unless `X-Option-Disable-Url-Parameter` is set.

| Tool | Summary (verbatim) | Parameters (default / max) |
|---|---|---|
| `analyze_catalog` | "Analyze the structure and composition of a portal catalog using ODSQL." | `select` (default `slug, asset_type, title, updated_at`), `where`, `order_by` (default `updated_at DESC`), `group_by`, `limit` (10 / max 100, min 0), `offset` (0), `facet` (comma list; "Set `limit=0` to skip fetching the asset listing entirely") |
| `search_assets` | "Search assets on a portal using the Explore API." | `query` ("Full-text search query used to find matching assets via vector similarity. Do not set this parameter for listing everything."), `limit` (5 / max 100), `offset` (0) |
| `get_asset` | "Retrieve a single asset by its slug using the Explore API." | `slug` (required). The description says it "Returns the asset description, field schema, and — for dataset assets — sample records and available export formats." |
| `search_asset_records` | "Retrieve records of a specific asset given its slug." | `slug` (required), `select` (default `*`), `where`, `order_by`, `group_by` ("When used, limit can go up to 20000."), `limit` (10 / max 100), `offset` (0) |

Notable verbatim details from `search_asset_records`:
- Geocoding happens on the server, France only: "Location-based queries are supported directly (only for places in France):`where=around(geo_field, \"Nantes\", 5km)` resolves the place name server-side".
- Default radius: "omitting it falls back to a broad 20km."
- Field names come from `get_asset`: "field names returned by `get_asset` can be used directly in ODSQL clauses here."

Tool set `old` (pre-2.0): its schemas are **not** in openapi.json, and `tools/list` could not be called without a key. The only public list is an **image** on X8 (`/assets/theme_image/outils_disponibles_mcp.png`). It names `explore_api_documentation` ("Récupérer la documentation de l'API Explore."), `explore_get_datasets`, `explore_get_dataset`, `explore_get_dataset_records`. Status: VERIFIED that the image shows these names. INFERRED that this is the `old` set, since 3 of the names match the renamed tools in X1.

### G.2 Public endpoint test for data.education.gouv.fr (live, 2026-11-11)

| Request (no credentials sent) | Result |
|---|---|
| `POST /mcp` `initialize`, no headers | `401 {"detail":"authentication failed: missing x-domain and x-apikey/x-token headers"}` |
| same + `X-Domain: https://data.education.gouv.fr` | 401, same message |
| same with `?x-domain=https://data.education.gouv.fr` | 401, same message |
| same + empty `X-Apikey:` | 401, same message |
| `GET /tools/latest/search_assets?url=https://data.education.gouv.fr&limit=1` | 401, same message |

**Conclusion:** the endpoint is public and alive, but **no anonymous access**. `tools/list` was not obtained live. The tool list above comes from the official OpenAPI spec and X1.

How to get a key for data.education.gouv.fr (documented on X8): sign up on the portal, accept the CGU, then generate a key under the account's "Clés API" tab.
- "La configuration avec le serveur nécessite que vous soyez inscrit(e) sur le portail pour pouvoir générer une clé API sécurisée." (X8) → VERIFIED.
- Ministry config shown on X8: `"supergateway@3.4.3", "--streamableHttp", "https://mcp.huwise.com/mcp", "--header", "x-domain: https://data.education.gouv.fr", "--header", "x-apikey: CLE_API"`.

A real "Huwise MCP baseline" is possible only after someone creates a portal account and an API key (a user decision; not done here).

Update 11.11.2026, 21:40 UTC: the account owner created a portal account and a read-only API key. With `X-Domain` +
`X-Apikey`, `initialize` and `tools/list` succeed (server `mcp-server (latest)` 1.28.1, the same four tools), and
`search_asset_records` on `fr-en-annuaire-education` with `nom_commune="Dijon" and type_etablissement="Collège"` returns
`total_count: 23`. The key lives outside the repository (`~/.config/huwise/account.env`, mode 600) → VERIFIED; configuration A
now calls this server.

## H. Huwy / AI client

| Claim | Quote (verbatim) | URL | Checked | Status |
|---|---|---|---|---|
| What it is: an optional assistant built into the marketplace | "Huwy is an optional AI assistant built into the Huwise data marketplace experience." | X2 | 2026-11-11 | VERIFIED |
| How it works: it is an MCP **client** of the Huwise MCP Server | "Huwy connects to the platform through the Huwise MCP Server, which provides controlled, structured access to marketplace assets and tools." | X2 | 2026-11-11 | VERIFIED |
| Difference from the MCP server: Huwy is one of the agents the server powers | "Front end agents, such as the Huwy AI exploration agent" (listed under "Currently, the Huwise MCP server powers:") | P3 | 2026-11-11 | VERIFIED |
| Where it lives: homepage, catalog, product pages | "such as on the homepage, in the catalog, or on an individual product page." | X6 | 2026-11-11 | VERIFIED |
| UI form: a floating bubble widget that opens a chat window (iframe) | "Customize Huwy's floating bubble icon" / "Iframe alternative text (for screen readers)" | X3 | 2026-11-11 | VERIFIED |
| Visibility modes: Public / Authenticated (default) / Restricted | "Huwy is visible to all users , including anonymous visitors (not logged in)." (Public) / "Authenticated (default)" | X3 | 2026-11-11 | VERIFIED |
| Back-office name is "Explore Agent" | "in your back office, go to Portal > Data processing > \"Explore Agent.\"" | X3 | 2026-11-11 | VERIFIED |
| Quotas: monthly plan quota plus configurable daily quotas. Anonymous users counted by IP | "Anonymous users are identified by their IP address." | X3 | 2026-11-11 | VERIFIED |
| Languages: English or French only | "Huwy currently speaks only English or French." | X2 | 2026-11-11 | VERIFIED |
| Short-term memory only | "If you reload the page, the conversation will be lost." | X2 | 2026-11-11 | VERIFIED |
| No web browsing | "No. Huwy does not browse the internet." | X2 | 2026-11-11 | VERIFIED |
| The model can be chosen ("the AI model you select") | "nor the AI model you select to drive the feature." | X2 | 2026-11-11 | VERIFIED. Which models: UNKNOWN in official docs (IT Brief press coverage mentions OpenAI and Mistral, which is not an official source) |
| Huwy usage is tracked | "The platform therefore provides comprehensive tracking of all Huwy-related usage: API calls, user actions, integration into the data consumption funnel, and more." | X6 | 2026-11-11 | VERIFIED |
| Separate older add-on: "Explore data with AI" (AI Insights tab, per dataset, charts) | "When the feature is enabled, users will see a tab AI Insights next to the dataset's normal tabs." | X17 | 2026-11-11 | VERIFIED |

### H.1 data.education.gouv.fr: is Huwy visible?

| Observation | Exact text / value | Source | Checked | Status |
|---|---|---|---|---|
| Home page card offering an AI chat | Title "Poser une question". Description "Les données de l'éducation deviennent accessibles et compréhensibles autrement : posez une question et obtenez une réponse immédiate sans aucune manipulation." CTA "Discutez avec l'IA" | https://data.education.gouv.fr/pages/accueil/ (static HTML + Neo render) | 2026-11-11 | VERIFIED (UI text) |
| Home page card for MCP | Title "Connecter une IA". Description "Branchez directement le portail à votre environnement de travail. Grâce au standard MCP, votre intelligence artificielle accède à nos données et pourra vous répondre." CTA "Serveur MCP" → `/pages/connecter-une-ia/` | P5 | 2026-11-11 | VERIFIED (UI text) |
| The chat card is wired to the platform agent | the card has the attribute `ods-explore-agent-on-click` and class `fr-custom-card--agent` | P5 source | 2026-11-11 | INFERRED (that this is Huwy) |
| The agent is enabled in the portal config | `EXPLORE_AGENT_ENABLED: true`. `"agent": {"enabled": true, "llm_app_slug": "ministere-education-nationale-mistral", ..., "anonymous_mode": true}` | X8 page source | 2026-11-11 | INFERRED (config, not documentation. The slug suggests a Mistral-backed app, but that is not confirmed) |
| Agent backend hosts in the config | `"agents": {"widget_url": "https://static.huwise.com/agents/", "service_url": "https://agents-chat-api.huwise.com", "aud": "agents-api"}` | X8 page source | 2026-11-11 | INFERRED |
| Agent chat API root (live GET) | `{"name":"Agents Chat API","version":"0.1.0","endpoints":{"health":"/api/health","chat":"/api/{tenant_slug}/chat/stream", ...}}` | https://agents-chat-api.huwise.com/ | 2026-11-11 | VERIFIED (live response). Not documented. Not called beyond GET / |
| The word "Huwy" on the portal | **Not found** in the home page or the X8 HTML. The UI only says "IA" | P5, X8 | 2026-11-11 | VERIFIED (absence) |
| A floating chat bubble | **Not seen.** In Neo (cookies: necessary only), there was no bubble on the home page or `/explore/`. Clicking "Poser une question" opened no visible window and created no iframe within ~8 s | Neo render | 2026-11-11 | UNKNOWN why (lazy loading, consent, or a rendering problem in the agent browser) |
| A separate third-party "ChatMD" helper is linked from the home page | text "Aide à la découverte des données propulsée par ChatMD" → `https://chatmd.forge.apps.education.fr/#data-education` | P5 (Neo) | 2026-11-11 | VERIFIED (UI text). Not Huwise |
| A Wikit chat script is loaded | `<script src="https://semantics-chat.wikit.ai/chat-embed.js">` plus the platform bundle `wikitPropsUtils-*.js` | P5 (Neo) | 2026-11-11 | INFERRED (role unknown. Not documented by Huwise) |
| The Ministry uses the Huwise MCP server across several AI tools | "the French Ministry of National Education, which uses the Huwise MCP server across several AI tools." | P3 | 2026-11-11 | VERIFIED |

## I. Response + citation behaviour

| Claim | Quote (verbatim) | URL | Checked | Status |
|---|---|---|---|---|
| Huwy outputs Markdown text only (no charts yet) | "For now, Huwy can only generate formatted text responses (Markdown) based on the data it has access to through our MCP server" | X2 | 2026-11-11 | VERIFIED |
| Concise, not exhaustive. Calculations stay consistent when the question is well scoped | "When a question is clearly scoped, however, any calculated results will be consistent." | X2 | 2026-11-11 | VERIFIED |
| Users are told to ask for the reasoning | "When a result is unclear or surprising, ask: “How did you arrive at this result?”" | X2 | 2026-11-11 | VERIFIED |
| Answers are a starting point, not a conclusion | "Treat answers as a starting point for exploration, not as a definitive conclusion." | X2 | 2026-11-11 | VERIFIED |
| "Explore data with AI" has a Show reasoning button and 4 output forms | "Use the Show reasoning button to understand or help verify the answer you were given." | X17 | 2026-11-11 | VERIFIED |
| Explore API responses carry navigation links (`_links`) that a client could cite | "All responses contain a list of links allowing easy and relevant navigation through the API endpoints." | P6 | 2026-11-11 | VERIFIED (API). Whether Huwy shows them: UNKNOWN |
| Huwy cites the dataset / record / query it used | **No official page found that says so** | — | 2026-11-11 | UNKNOWN |
| MCP tool output format (fields, citations) | openapi.json response schema is `{}` (untyped) for every tool | P2 | 2026-11-11 | UNKNOWN |

---

## Known unknowns (not public as of 2026-11-11)

1. Internal storage and indexing engine behind the Explore API and the catalog (database, search index, vector store, embedding model).
2. Search and recommendation ranking: how vector search, "usage-driven discovery" ("the most useful data is shown first, based on each user’s profile", P1) and boosting are computed.
3. Living Context Layer internals: data model, how signals are stored, weighted, aggregated and expired; what the "usage matrix" (X7) contains; which context is exposed to agents via MCP and in which fields.
4. Whether failed (zero-result) searches are exposed to agents/MCP. Only P1 marketing text and X9 analytics (result counts per term) mention them.
5. Huwy: which LLM(s) and providers; prompt/orchestration; tool-calling loop; which MCP tool set it uses; citation format; how it applies anonymous mode. The data.education.gouv.fr slug `ministere-education-nationale-mistral` is config only.
6. Agent orchestration for the turnkey agents (Marketplace Curator, Opportunity Spotter, Data Product Builder/Designer, Metadata Filler) and the "agentic framework": runtime, scheduling, and how they write back.
7. The MCP server's output schema (the responses are untyped in OpenAPI), rate limits/quotas for MCP calls, and the exact difference between `latest` and `beta` (identical in the spec today).
8. The `old` tool set's live schemas (only an image is public); whether `explore_api_documentation` still exists.
9. What `/rw/vaf/events` collects on portals, and how it feeds the context layer.
10. The role of the Wikit script and of the "ChatMD" helper on data.education.gouv.fr, and why the Huwy bubble did not render in the agent browser.
11. Security certifications / hosting region (the security page was not checked in this pass).
12. Why the dataset count differs on data.education.gouv.fr (UI "Données 285" vs API `total_count` 314).

---

## Machine-friendly summary

```json
{
  "checked": "2026-11-11",
  "components": [
    {"id": "A", "name": "External Data Sources", "status": "VERIFIED", "urls": ["https://www.huwise.com/en/integration-connectivity/", "https://www.huwise.com/en/blog/huwy-ai-agent-for-smart-data-exploration/", "https://userguide.huwise.com/en/articles/2022658"], "summary": "~80 connectors plus harvesters (CKAN, ArcGIS, Huwise Federation); virtualized access to Snowflake/Databricks without duplication."},
    {"id": "B", "name": "Ingestion & Publication", "status": "VERIFIED", "urls": ["https://www.huwise.com/en/integration-connectivity/", "https://www.huwise.com/en/api-export/", "https://userguide.huwise.com/en/articles/2033090"], "summary": "Import with preview, processors transform data, each published dataset gets an auto-generated API; internal pipeline undocumented."},
    {"id": "C", "name": "Data Marketplace / Asset Catalog", "status": "VERIFIED", "urls": ["https://www.huwise.com/en/living-context-layer/", "https://userguide.huwise.com/en/articles/5071874", "https://userguide.huwise.com/en/articles/2257730", "https://data.education.gouv.fr/explore/"], "summary": "Catalog of assets (datasets, visualizations, showcases, pages, reuses) with AI vector search; data.education.gouv.fr shows 370 assets in UI, API total_count 314 datasets."},
    {"id": "D", "name": "Living Context Layer", "status": "VERIFIED", "urls": ["https://www.huwise.com/en/living-context-layer/", "https://www.huwise.com/en/blog/huwise-agentic-framework-data-marketplaces/", "https://www.huwise.com/en/blog/huwise-mcp-agentic-ai/", "https://userguide.huwise.com/en/articles/2040578", "https://userguide.huwise.com/en/articles/10271554"], "summary": "Supply (assets, schemas, definitions, lineage) + demand signals: searches incl. unsuccessful, views, exports, access requests, corrections, drop-offs, user journeys, questions, agent actions via MCP; internals unknown; feedback not named."},
    {"id": "E", "name": "Governance & Security", "status": "VERIFIED", "urls": ["https://www.huwise.com/en/living-context-layer/", "https://www.huwise.com/en/blog/huwise-mcp-agentic-ai/", "https://userguide.huwise.com/en/articles/2043458", "https://userguide.huwise.com/en/articles/2041602", "https://userguide.huwise.com/en/articles/2044226", "https://www.huwise.com/en/user-access-management/"], "summary": "User permissions apply to every request incl. agents/MCP/Huwy; field+row filters, per-user API limits, groups, MFA, SSO; API keys per workspace carry user rights."},
    {"id": "F", "name": "Explore API / ODSQL", "status": "VERIFIED", "urls": ["https://help.opendatasoft.com/apis/ods-explore-v2/explore_v2.1.html", "https://data.education.gouv.fr/api/explore/v2.1/swagger.json", "https://userguide.huwise.com/en/articles/2257410"], "summary": "GET-only REST /api/explore/v2.1; records endpoint with select/where/group_by/order_by/limit/offset; limit<=100 (<=20000 with group_by), offset+limit<10000; total_count+results; exports unlimited (csv, json, parquet, geojson, ...)."},
    {"id": "G", "name": "Huwise MCP Server", "status": "VERIFIED", "urls": ["https://mcp.huwise.com/docs", "https://mcp.huwise.com/openapi.json", "https://userguide.huwise.com/en/articles/5071874", "https://data.education.gouv.fr/pages/connecter-une-ia/"], "summary": "POST https://mcp.huwise.com/mcp, StreamableHTTP stateless; headers X-Domain + X-Apikey (or X-Token); tools analyze_catalog, search_assets, get_asset, search_asset_records; anonymous calls return 401, so a portal API key is required."},
    {"id": "H", "name": "Huwy / AI client", "status": "VERIFIED", "urls": ["https://userguide.huwise.com/en/articles/6504002", "https://userguide.huwise.com/en/articles/9811266", "https://www.huwise.com/en/blog/huwy-ai-agent-for-smart-data-exploration/", "https://data.education.gouv.fr/pages/accueil/"], "summary": "Optional in-portal chat widget ('Explore Agent') that is an MCP client of the Huwise MCP server; EN/FR, short-term memory, quotas; data.education.gouv.fr shows 'Poser une question / Discutez avec l'IA' card, agent enabled in config, name 'Huwy' not shown, bubble not observed."},
    {"id": "I", "name": "Response + citation behaviour", "status": "UNKNOWN", "urls": ["https://userguide.huwise.com/en/articles/6504002", "https://userguide.huwise.com/en/articles/2730498"], "summary": "Huwy answers in Markdown, concise, consistent when scoped, users told to ask how it arrived at the result; no official statement that it cites datasets/records."}
  ]
}
```
