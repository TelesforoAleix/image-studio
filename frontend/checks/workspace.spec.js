import { test, expect } from "@playwright/test";

async function workspace(page, { empty = false, references = [] } = {}) {
  const profile = (name) => ({
    display_name: name,
    licence: "Apache-2.0",
    seconds_per_image: 12,
    max_references: 4,
    reference_slots: { character: 2, object: 3 },
    aspect_ratios: { values: ["1:1", "16:9"] },
    qualities: { values: ["standard", "high"] },
    price_per_image: { standard: 0.01, high: 0.03 },
    advanced: [{ name: "detail", type: "integer", default: 1, range: [1, 4] }],
  });
  const models = [
    { model_name: "alpha", model_info: profile("Alpha") },
    { model_name: "beta", model_info: profile("Beta") },
    {
      model_name: "square",
      model_info: {
        ...profile("Square only"),
        aspect_ratios: { values: ["1:1"] },
      },
    },
  ];
  const feedback = () => ({
    verdict: null,
    asset_ratings: [],
    note: "",
    updated_at: null,
  });
  const makeRun = (id, model, format, count, time) => ({
    run_id: id,
    created_at: time,
    references: [],
    generations: [
      {
        id: id === "latest" ? 2 : 1,
        model,
        model_info: models.find((m) => m.model_name === model).model_info,
        state: "done",
        outputs: [`output-${id}`],
        feedback: [feedback()],
        count,
        references: [],
        created_at: time,
        assembled_prompt: `Synthetic ${id} content`,
        rendered_prompt: `Synthetic ${id} rendered`,
        prompt: `Synthetic ${id} edited`,
        edited: true,
        settings: { format, quality: "high", advanced: { detail: 3 } },
        request_fields: { synthetic: true },
      },
    ],
  });
  const state = {
    comp: {
      id: 1,
      name: "Synthetic composition",
      project_id: 1,
      kind: "storyboard",
      sequences: [],
      brief: "Synthetic scene",
      assets: [],
      style: null,
      style_deselected_images: [],
      variants: [1, 2, 3].map((id) => ({
        id,
        name: `Frame ${id}`,
        instructions: "",
        use_previous_frame: true,
        deselected_images: [],
        selected_originals: [],
        final: null,
      })),
    },
    runs: empty
      ? []
      : [
          makeRun("latest", "alpha", "16:9", 2, "2026-10-15T12:00:00Z"),
          makeRun("earlier", "beta", "1:1", 1, "2026-10-15T11:00:00Z"),
        ],
    others: [],
    posts: [],
    sequencePosts: [],
    patches: [],
    orders: [],
    references,
    holdSave: null,
    failSave: false,
    events: [],
    feedbackRequests: [],
    assetGenerations: [],
    holdRuns: null,
  };
  const asset = {
    id: 10,
    name: "Lamp",
    type: "object_vehicle",
    images: [1, 2].map((id) => ({
      id,
      hash: `lamp-${id}`,
      approved: id === 1,
      source: "uploaded",
      rejected: false,
    })),
    references: [],
    originals: [],
  };
  state.asset = asset;
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname.slice(4),
      method = req.method();
    let value;
    if (path === "/projects") value = [{ id: 1, name: "Synthetic project" }];
    else if (path === "/projects/1/assets") value = [asset];
    else if (path === "/models") value = models;
    else if (path === "/assets")
      value = [
        { id: 10, name: "Lamp", type: "object_vehicle", thumbnail: "lamp-1" },
      ];
    else if (path === "/assets/10") value = asset;
    else if (path === "/compositions/1") {
      if (method === "PATCH") {
        state.events.push("save-start");
        if (state.holdSave) await state.holdSave;
        if (state.failSave)
          return route.fulfill({
            status: 400,
            json: { error: "Synthetic save failed" },
          });
        const patch = req.postDataJSON();
        state.patches.push(patch);
        Object.assign(state.comp, patch);
        state.events.push("saved");
      }
      value = state.comp;
    } else if (path === "/compositions/1/frame-sequences") {
      const body = req.postDataJSON();
      state.sequencePosts.push(body);
      const start =
        body.mode === "full"
          ? 0
          : body.mode === "next"
            ? body.frame_id
            : body.frame_id - 1;
      const ids = body.mode === "next" ? [start + 1] : [1, 2, 3].slice(start);
      const seq = {
        id: 1,
        state: "running",
        current_frame: 0,
        frames: ids.map((id, i) => ({
          frame_id: id,
          state: i ? "waiting" : "running",
          run_id: i ? null : "sequence-run",
        })),
      };
      state.comp.sequences = [seq];
      value = seq;
    } else if (path === "/frame-sequences/1/stop") {
      state.comp.sequences[0].state = "stopping";
      value = state.comp.sequences[0];
    } else if (path === "/compositions/1/assets/10") {
      if (method === "PUT")
        state.comp.assets = [
          {
            id: 10,
            asset_id: 10,
            asset,
            deselected_images: [],
            selected_originals: [],
            ...req.postDataJSON(),
          },
        ];
      else state.comp.assets = [];
      value = state.comp;
    } else if (path === "/compositions/1/frame-order") {
      const { ids } = req.postDataJSON();
      state.orders.push(ids);
      state.comp.variants.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id));
      value = state.comp;
    } else if (/^\/variants\/\d+$/.test(path)) {
      const frame = state.comp.variants.find(
        (f) => f.id === Number(path.split("/")[2]),
      );
      if (method === "PATCH") Object.assign(frame, req.postDataJSON());
      value = { ...frame, composition_id: 1 };
    } else if (path === "/assets/10/generations")
      value = state.assetGenerations;
    else if (path === "/assets/10/reference-preview")
      value = { prompt: "Synthetic reference", references: [] };
    else if (path.endsWith("/preview"))
      value = {
        prompt: req.postDataJSON().brief,
        references: state.references.filter(
          (r) =>
            r.role !== "previous frame" ||
            state.comp.variants.find((f) => f.id === Number(path.split("/")[2]))
              .use_previous_frame,
        ),
        previous_frame: state.references.find(
          (r) => r.role === "previous frame",
        ),
      };
    else if (path === "/render") {
      const body = req.postDataJSON();
      value = body.models.map((c) => ({
        model: c.model,
        rendered_prompt: `${c.model}: ${body.content}`,
        references: body.references,
        estimated_cost: 0.03 * c.count,
      }));
    } else if (path === "/spend") value = { estimated_spend: 0.12 };
    else if (/^\/variants\/\d+\/runs$/.test(path)) {
      if (method === "POST") {
        const body = req.postDataJSON();
        state.posts.push(body);
        state.events.push("queued");
        const run = {
          run_id: "queued",
          created_at: new Date().toISOString(),
          references: body.references || state.references,
          generations: body.models.map((c, i) => ({
            id: 20 + i,
            ...c,
            model_info: models.find((m) => m.model_name === c.model).model_info,
            state: "waiting",
            outputs: [],
            feedback: [],
            references: body.references || state.references,
            assembled_prompt: state.comp.brief,
            prompt: c.prompt || state.comp.brief,
            settings: c.settings,
            started_at: new Date().toISOString(),
          })),
        };
        state.runs.unshift(run);
        value = run;
      } else {
        if (state.holdRuns) await state.holdRuns;
        value = path === "/variants/1/runs" ? state.runs : state.others;
      }
    } else if (/^\/variants\/\d+\/final$/.test(path)) {
      const frame = state.comp.variants.find(
        (f) => f.id === Number(path.split("/")[2]),
      );
      if (method === "PUT") {
        const body = req.postDataJSON(),
          g = state.runs
            .flatMap((r) => r.generations)
            .find((g) => g.id === body.generation_id);
        frame.final = { ...body, hash: g.outputs[body.output] };
      }
      if (method === "DELETE") frame.final = null;
      value = frame.final;
    } else if (path.includes("/feedback")) {
      const [, id, output] = /generations\/(\d+)\/outputs\/(\d+)/.exec(path);
      const g = [
        ...state.runs.flatMap((r) => r.generations),
        ...state.assetGenerations,
      ].find((g) => g.id === Number(id));
      const body = req.postDataJSON();
      state.feedbackRequests.push({
        id: Number(id),
        output: Number(output),
        body,
      });
      value = {
        ...g.feedback[output],
        ...body,
        updated_at: new Date().toISOString(),
      };
      g.feedback[output] = value;
    } else if (/^\/generations\/\d+$/.test(path)) {
      const id = Number(path.split("/")[2]);
      value = [
        ...state.runs.flatMap((r) => r.generations),
        ...state.assetGenerations,
      ].find((g) => g.id === id);
      value = { variant_id: 1, ...value };
    } else if (path.startsWith("/files/"))
      return route.fulfill({
        contentType: "image/svg+xml",
        body: `<svg xmlns="http://www.w3.org/2000/svg" width="${40 + path.length}" height="40"><rect width="100%" height="100%" fill="olive"/></svg>`,
      });
    else throw new Error(`Unexpected synthetic request: ${method} ${path}`);
    await route.fulfill({ json: value });
  });
  return state;
}
const open = (page) => page.goto("/#composition/1/frame/1");
const generate = (page) =>
  page.getByRole("button", { name: "Generate", exact: true });

test("one iteration beside the words, prompt edits, progress, feedback and finals without navigation", async ({
  page,
}) => {
  const state = await workspace(page);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await open(page);
  await expect(page.locator(".model-chip > summary")).toContainText(
    "Alpha · 2 outputs · high",
  );
  await page
    .getByRole("textbox", { name: "Brief" })
    .fill("Synthetic changed scene");
  await expect(
    page
      .getByRole("textbox", { name: "Brief" })
      .locator("..")
      .getByRole("status"),
  ).toHaveText("Saved");
  expect(state.comp.brief).toBe("Synthetic changed scene");
  await page.getByText("+ model", { exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "Square only" }),
  ).toBeDisabled();
  await expect(page.getByText("Does not support 16:9")).toBeVisible();
  await page.getByRole("checkbox", { name: "Beta", exact: true }).check();
  await page.getByText("+ model", { exact: true }).click();
  await page.getByRole("button", { name: "View prompts (2)" }).click();
  const sheet = page.getByRole("dialog", { name: "View prompts" });
  const dockBounds = await page.locator(".generate-bar").boundingBox();
  const sheetBounds = await sheet.boundingBox();
  expect(sheetBounds.y + sheetBounds.height).toBeLessThanOrEqual(
    dockBounds.y + 1,
  );
  expect((await page.locator(".filmstrip").boundingBox()).height).toBeLessThan(
    210,
  );
  await expect(
    sheet.getByText("alpha: Synthetic changed scene", { exact: true }),
  ).toBeVisible();
  await sheet
    .getByRole("button", { name: "Edit", exact: true })
    .first()
    .click();
  await sheet
    .getByRole("textbox", { name: "Prompt for Alpha" })
    .fill("Synthetic local edit");
  await page.getByRole("button", { name: "Close prompts" }).click();
  await expect(page.locator(".model-chip").first()).toContainText(
    "Edited prompt",
  );
  await expect(generate(page)).toBeEnabled();
  await generate(page).click();
  await expect.poll(() => state.posts.length).toBe(1);
  expect(state.posts[0].models[0].prompt).toBe("Synthetic local edit");
  expect(state.posts[0].models[1].prompt).toBeUndefined();
  await expect(
    page
      .locator(".workspace-results article")
      .getByText(/Waiting for the image service/),
  ).toHaveCount(2);
  state.runs[0].generations.forEach((g) => {
    g.state = "running";
  });
  await expect(
    page.locator(".workspace-results article").getByText(/about \d+ s left/),
  ).toHaveCount(2);
  state.runs[0].generations.forEach((g) => {
    g.state = "done";
    g.outputs = [`new-${g.id}`];
    g.feedback = [{ verdict: null, asset_ratings: [], note: "" }];
  });
  await expect(
    page.getByRole("button", { name: "Mark final", exact: true }),
  ).toHaveCount(2);
  await page
    .getByRole("button", { name: "Mark final", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: "Final", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("img", { name: "Frame 1 final" })).toBeVisible();
  await page.getByRole("button", { name: "Good", exact: true }).first().click();
  await expect(
    page.getByRole("button", { name: "Good", exact: true }).first(),
  ).toHaveAttribute("aria-pressed", "true");
  expect(page.url()).toMatch(/#composition\/1\/frame\/1$/);
  await expect(page.locator("button.primary")).toHaveCount(1);
  expect(errors).toEqual([]);
});

test("earlier run selection, pinned reuse, restore current and remember latest on reopen", async ({
  page,
}) => {
  const state = await workspace(page);
  await open(page);
  await expect(page.locator(".model-chip > summary")).toContainText(
    "Alpha · 2 outputs · high",
  );
  await expect(page.locator(".model-chip > summary")).not.toContainText(
    "Edited prompt",
  );
  await page.locator(".run-strip button").last().click();
  await expect(page.locator(".workspace-results article h3").last()).toHaveText(
    "Beta",
  );
  await page.getByRole("button", { name: "Reuse settings" }).click();
  await expect(page.locator(".reuse-chip")).toContainText("Reused from");
  await expect(page.locator(".model-chip > summary")).toContainText(
    "Beta · 1 outputs · high",
  );
  await expect(
    page.getByRole("combobox", { name: "Format", exact: true }),
  ).toHaveValue("1:1");
  await page.getByRole("button", { name: "View prompts (1)" }).click();
  await expect(
    page.getByRole("textbox", { name: "Prompt for Beta" }),
  ).toHaveValue("Synthetic earlier edited");
  await page.getByRole("button", { name: "Close prompts" }).click();
  await page
    .getByRole("button", { name: "Back to current", exact: true })
    .click();
  await expect(page.locator(".model-chip > summary")).toContainText(
    "Alpha · 2 outputs · high",
  );
  await expect(
    page.getByRole("combobox", { name: "Format", exact: true }),
  ).toHaveValue("16:9");
  await page.reload();
  await expect(page.locator(".model-chip > summary")).toContainText(
    "Alpha · 2 outputs · high",
  );
  await page.locator(".model-chip > summary").click();
  await page.getByText("Advanced", { exact: true }).click();
  await expect(page.getByLabel("detail", { exact: true })).toHaveValue("3");
  state.runs = [];
  state.others = [
    {
      ...{
        run_id: "other",
        created_at: "2026-10-15T10:00:00Z",
        references: [],
        generations: [
          {
            model: "beta",
            count: 3,
            settings: {
              format: "1:1",
              quality: "standard",
              advanced: { detail: 2 },
            },
          },
        ],
      },
    },
  ];
  await page.reload();
  await expect(page.locator(".model-chip > summary")).toContainText(
    "Beta · 3 outputs · standard",
  );
});

test("filmstrip drag and keyboard reorder submit the complete set", async ({
  page,
}) => {
  const state = await workspace(page);
  await open(page);
  const cards = page.locator(".frame-card");
  await cards.nth(2).dragTo(cards.nth(0));
  await expect.poll(() => state.orders).toEqual([[3, 1, 2]]);
  await expect(cards.first()).toContainText("Frame 3");
  await cards.first().getByRole("link").focus();
  await page.keyboard.press("Alt+ArrowRight");
  await expect
    .poll(() => state.orders)
    .toEqual([
      [3, 1, 2],
      [1, 3, 2],
    ]);
  await expect(cards.nth(1)).toContainText("Frame 3");
  await expect(cards.nth(1).getByRole("link")).toBeFocused();
});

test("reference totals name model limits and slots; pack picker has names and thumbnails", async ({
  page,
}) => {
  const references = Array.from({ length: 5 }, (_, i) => ({
    asset_id: i + 1,
    asset_name: `Synthetic ${i}`,
    hash: `ref-${i}`,
    type: "person",
    role: "subject",
  }));
  await workspace(page, { references });
  await open(page);
  await expect(
    page.getByText("5 references selected", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Alpha: selected 5 references; accepts at most 4."),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Alpha: selected 5 character references; accepts at most 2.",
    ),
  ).toBeVisible();
  await expect(generate(page)).toBeDisabled();
  await page.getByRole("button", { name: "Add asset", exact: true }).click();
  await page.getByRole("textbox", { name: "Search assets" }).fill("lamp");
  await expect(page.locator(".asset-pick img")).toBeVisible();
  await page.getByRole("button", { name: "Lamp · Object/Vehicle" }).click();
  await page.locator(".pack-row").getByText("Images", { exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "Lamp, reference 1 of 1" }),
  ).toBeChecked();
  await expect(
    page.getByRole("checkbox", { name: "Lamp, original 1 of 1" }),
  ).not.toBeChecked();
});

test("toolbar menus have keyboard navigation, escape, exports and inline delete", async ({
  page,
}) => {
  const state = await workspace(page);
  await open(page);
  const share = page.getByRole("button", { name: "Share", exact: true });
  await share.focus();
  await page.keyboard.press("ArrowDown");
  await expect(
    page.getByRole("menuitem", { name: "Export images" }),
  ).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(
    page.getByRole("menuitem", { name: "Export package" }),
  ).toBeFocused();
  await expect(
    page.getByRole("menuitem", { name: "Export package" }),
  ).toHaveAttribute("href", "/api/compositions/1/export.zip");
  await expect(
    page.getByText(
      /Export images skips frames without finals: Frame 1, Frame 2, Frame 3/,
    ),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(share).toBeFocused();
  await expect(page.getByRole("menu")).toHaveCount(0);
  const more = page.getByRole("button", { name: "⋯", exact: true });
  await more.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Duplicate" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(
    page.getByRole("menuitem", { name: "Move to project…" }),
  ).toBeFocused();
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("button", { name: "Yes, delete composition" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await more.click();
  await page.keyboard.press("Escape");
  await expect(more).toBeFocused();
  await more.click();
  await page.getByRole("menuitem", { name: "Move to project…" }).click();
  state.failSave = true;
  await page
    .getByRole("combobox", { name: "Move to project" })
    .selectOption("");
  await expect(page.getByRole("alert")).toHaveText("Synthetic save failed");
  state.failSave = false;
  await page
    .getByRole("combobox", { name: "Move to project" })
    .selectOption("");
  await expect(page.locator(".breadcrumb")).toContainText("No project");
  await page.getByRole("button", { name: "Done moving" }).click();
  for (const suffix of ["setup", "generate", "history"]) {
    await page.goto(`/#composition/1/frame/1/${suffix}`);
    await expect(page).toHaveURL(/#composition\/1\/frame\/1$/);
    await expect(page.locator("button.primary")).toHaveCount(1);
    await expect(
      page.getByRole("navigation", { name: "Composition tabs" }),
    ).toHaveCount(0);
  }
});

test("autosave flushes before queue and navigation; failure stays beside the field", async ({
  page,
}) => {
  const state = await workspace(page);
  await open(page);
  await expect(generate(page)).toBeEnabled();
  let release;
  state.holdSave = new Promise((resolve) => {
    release = resolve;
  });
  await page
    .getByRole("textbox", { name: "Brief" })
    .fill("Synthetic immediate scene");
  await generate(page).click();
  await expect.poll(() => state.events.includes("save-start")).toBe(true);
  expect(state.posts).toHaveLength(0);
  state.holdSave = null;
  release();
  await expect.poll(() => state.posts.length).toBe(1);
  expect(state.events.indexOf("saved")).toBeLessThan(
    state.events.indexOf("queued"),
  );
  state.failSave = true;
  await page
    .getByRole("textbox", { name: "Brief" })
    .fill("Synthetic failed edit");
  await expect(
    page
      .getByRole("textbox", { name: "Brief" })
      .locator("..")
      .getByRole("status"),
  ).toHaveText("Synthetic save failed");
  await page.getByRole("link", { name: "2. Frame 2", exact: false }).click();
  await expect(page).toHaveURL(/#composition\/1\/frame\/1$/);
  state.failSave = false;
  await page.getByRole("link", { name: "2. Frame 2", exact: false }).click();
  await expect(page).toHaveURL(/#composition\/1\/frame\/2$/);
  expect(state.comp.brief).toBe("Synthetic failed edit");
});

test("empty single has no frame overrides, keyboard generation flushes, and browser navigation waits", async ({
  page,
}) => {
  const state = await workspace(page, { empty: true });
  await page.setViewportSize({ width: 1280, height: 800 });
  state.comp.kind = "single";
  state.comp.variants = [state.comp.variants[0]];
  await open(page);
  await expect(page.locator(".model-chip")).toHaveCount(0);
  await expect(page.getByText("This frame only", { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("textbox", { name: "What happens in this frame" }),
  ).toHaveCount(0);
  await expect(page.locator(".filmstrip")).toHaveCount(0);
  await page.getByRole("button", { name: "⋯", exact: true }).click();
  await page.getByRole("menuitem", { name: "Make storyboard" }).click();
  await expect(page.locator(".filmstrip")).toBeVisible();
  await page.getByRole("button", { name: "⋯", exact: true }).click();
  await page.getByRole("menuitem", { name: "Make single image" }).click();
  await expect(page.locator(".filmstrip")).toHaveCount(0);
  await page.getByText("+ model", { exact: true }).click();
  await page.getByRole("checkbox", { name: "Alpha", exact: true }).check();
  await page.getByText("+ model", { exact: true }).click();
  await expect(generate(page)).toBeEnabled();
  await page
    .getByRole("textbox", { name: "Brief" })
    .fill("Synthetic keyboard scene");
  await page.keyboard.press("Control+Enter");
  await expect.poll(() => state.posts.length).toBe(1);
  expect(state.comp.brief).toBe("Synthetic keyboard scene");
  let release;
  state.holdSave = new Promise((resolve) => {
    release = resolve;
  });
  await page
    .getByRole("textbox", { name: "Brief" })
    .fill("Synthetic navigation scene");
  await page.evaluate(() => {
    location.hash = "composition/1/frame/999";
  });
  await expect
    .poll(() => state.events.filter((e) => e === "save-start").length)
    .toBeGreaterThan(1);
  await expect(page.getByRole("textbox", { name: "Brief" })).toHaveValue(
    "Synthetic navigation scene",
  );
  state.holdSave = null;
  release();
  await expect.poll(() => state.comp.brief).toBe("Synthetic navigation scene");
  await expect(page).toHaveURL(/#composition\/1\/frame\/1$/);
});

function viewerRun(state) {
  const g = state.runs[0].generations[0];
  g.outputs.push("synthetic-second");
  g.feedback.push({ verdict: null, asset_ratings: [], note: "" });
  state.runs[0].generations.push({
    ...structuredClone(g),
    id: 3,
    model: "beta",
    model_info: { ...g.model_info, display_name: "Beta" },
    outputs: ["synthetic-beta"],
    feedback: [{ verdict: null, asset_ratings: [], note: "" }],
  });
}
const viewer = (page) => page.getByRole("dialog", { name: "Output viewer" });

test("viewer keyboard crosses models and runs, traps focus and retains the workspace place", async ({
  page,
}) => {
  const state = await workspace(page);
  viewerRun(state);
  await open(page);
  await page
    .getByRole("textbox", { name: "Brief", exact: true })
    .fill("Synthetic retained draft");
  await page.getByRole("button", { name: "Add asset", exact: true }).click();
  await page
    .getByRole("textbox", { name: "Search assets" })
    .fill("retained search");
  const link = page.locator(".workspace-results a[data-output]").first();
  await link.focus();
  const scroll = await page.evaluate(() => ({
    window: scrollY,
    results: document.querySelector(".workspace-results").scrollTop,
  }));
  await link.click();
  await expect(viewer(page)).toBeVisible();
  await expect(page).toHaveURL(/\?output=2\.0$/);
  await expect(viewer(page).locator(".viewer-image img")).toHaveAttribute(
    "src",
    "/api/files/output-latest",
  );
  await expect
    .poll(
      async () =>
        (await viewer(page).locator(".viewer-image img").boundingBox()).height,
    )
    .toBeGreaterThan(500);
  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(/output=2\.1$/);
  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(/output=3\.0$/);
  await page.keyboard.press("ArrowLeft");
  await expect(page).toHaveURL(/output=2\.1$/);
  await page.keyboard.press("ArrowUp");
  await expect(page).toHaveURL(/output=1\.0$/);
  await page.keyboard.press("ArrowDown");
  await expect(page).toHaveURL(/output=2\.0$/);
  for (const name of [
    "← Previous output",
    "Next output →",
    "↑ Previous run",
    "↓ Next run",
    "Good G",
    "Not good N",
    "Mark final F",
    "Provide feedback Enter",
    "Compare C",
    "Close Esc",
  ])
    await expect(
      viewer(page).getByRole("button", { name, exact: true }),
    ).toBeVisible();
  await viewer(page)
    .getByRole("button", { name: "Close Esc", exact: true })
    .focus();
  for (let i = 0; i < 18; i++) {
    await page.keyboard.press("Tab");
    expect(
      await page.evaluate(() =>
        document.querySelector("dialog").contains(document.activeElement),
      ),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(viewer(page)).toHaveCount(0);
  await expect(link).toBeFocused();
  await expect(
    page.getByRole("textbox", { name: "Brief", exact: true }),
  ).toHaveValue("Synthetic retained draft");
  await expect(
    page.getByRole("textbox", { name: "Search assets" }),
  ).toHaveValue("retained search");
  expect(
    await page.evaluate(() => ({
      window: scrollY,
      results: document.querySelector(".workspace-results").scrollTop,
    })),
  ).toEqual(scroll);
  await expect(page.locator(".run-strip button").first()).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

test("viewer G N F Enter update requests and results, forms take Escape first, polling stays usable", async ({
  page,
}) => {
  const state = await workspace(page);
  viewerRun(state);
  state.runs[0].generations[0].references = [
    { asset_id: 10, asset_name: "Synthetic subject", role: "subject" },
  ];
  state.runs[1].generations[0].state = "running";
  await open(page);
  await page.locator(".workspace-results a[data-output]").first().click();
  await expect(viewer(page)).toBeVisible();
  let release;
  state.holdRuns = new Promise((resolve) => {
    release = resolve;
  });
  await page.keyboard.press("g");
  await expect(
    viewer(page).getByRole("button", { name: "Good G", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("g");
  await expect(
    viewer(page).getByRole("button", { name: "Good G", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await page.keyboard.press("n");
  await expect(
    viewer(page).getByRole("button", { name: "Not good N", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("f");
  await expect(
    viewer(page).getByRole("button", { name: "Final F", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(state.comp.variants[0].final).toMatchObject({
    generation_id: 2,
    output: 0,
  });
  await page.keyboard.press("Enter");
  await viewer(page)
    .getByRole("textbox", { name: "Note (optional)" })
    .fill("gnf Synthetic note");
  await page.keyboard.press("Escape");
  await expect(
    viewer(page).getByRole("textbox", { name: "Note (optional)" }),
  ).toHaveCount(0);
  await expect(viewer(page)).toBeVisible();
  await page.keyboard.press("Enter");
  await viewer(page)
    .getByRole("textbox", { name: "Note (optional)" })
    .fill("Synthetic detailed note");
  await viewer(page)
    .getByRole("combobox", { name: "Synthetic subject · subject" })
    .selectOption("kept");
  await page.keyboard.press("Control+Enter");
  expect(state.posts).toHaveLength(0);
  await viewer(page)
    .getByRole("button", { name: "Save feedback", exact: true })
    .click();
  await expect(
    viewer(page).getByRole("textbox", { name: "Note (optional)" }),
  ).toHaveCount(0);
  expect(state.feedbackRequests).toEqual([
    { id: 2, output: 0, body: { verdict: "good" } },
    { id: 2, output: 0, body: { verdict: null } },
    { id: 2, output: 0, body: { verdict: "not_good" } },
    {
      id: 2,
      output: 0,
      body: {
        verdict: "not_good",
        asset_ratings: [{ asset_id: 10, rating: "kept" }],
        note: "Synthetic detailed note",
      },
    },
  ]);
  await page.waitForTimeout(3200);
  await expect(
    viewer(page).getByRole("button", { name: "Good G", exact: true }),
  ).toBeEnabled();
  await expect(
    viewer(page).getByRole("button", { name: "Final F", exact: true }),
  ).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Not good", exact: true }).first(),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByRole("button", { name: "Final", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("img", { name: "Frame 1 final" })).toBeVisible();
  state.holdRuns = null;
  release();
});

test("compare fills three columns, focused final and custom picks across runs", async ({
  page,
}) => {
  const state = await workspace(page);
  viewerRun(state);
  await open(page);
  await page.locator(".workspace-results a[data-output]").first().click();
  await expect(viewer(page)).toBeVisible();
  await page.keyboard.press("c");
  await expect(viewer(page).locator(".viewer-image")).toHaveCount(3);
  const images = await viewer(page)
    .locator(".viewer-image")
    .evaluateAll((nodes) => nodes.map((n) => n.getBoundingClientRect().height));
  expect(images[0]).toBeGreaterThan(500);
  expect(new Set(images).size).toBe(1);
  await viewer(page)
    .getByRole("button", { name: "Focus Beta, output 1", exact: true })
    .click();
  await page.keyboard.press("g");
  await expect(
    viewer(page).getByRole("button", { name: "Good G", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("f");
  await expect(
    viewer(page).getByRole("button", { name: "Final F", exact: true }),
  ).toBeVisible();
  expect(state.comp.variants[0].final).toMatchObject({
    generation_id: 3,
    output: 0,
  });
  await page.keyboard.press("Escape");
  await expect(viewer(page).locator(".viewer-image")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await page
    .getByRole("checkbox", { name: "Compare Alpha, output 2", exact: true })
    .check();
  await page.locator(".run-strip button").last().click();
  await page
    .getByRole("checkbox", { name: "Compare Beta, output 1", exact: true })
    .check();
  await page.locator(".workspace-results a[data-output]").first().click();
  await expect(viewer(page)).toBeVisible();
  await page.keyboard.press("c");
  await expect(viewer(page).locator(".viewer-image")).toHaveCount(2);
  expect(
    await viewer(page)
      .locator(".viewer-image img")
      .evaluateAll((nodes) => nodes.map((n) => n.getAttribute("src"))),
  ).toEqual(["/api/files/output-earlier", "/api/files/synthetic-second"]);
});

test("old output links resolve their frame; Back closes, Forward opens and direct suffix closes safely", async ({
  page,
}) => {
  await workspace(page);
  await page.goto("/#output/2/0");
  await expect(viewer(page)).toBeVisible();
  await expect(page).toHaveURL(/#composition\/1\/frame\/1\?output=2\.0$/);
  await page.goBack();
  await expect(viewer(page)).toHaveCount(0);
  await expect(page).toHaveURL(/#composition\/1\/frame\/1$/);
  await page.goForward();
  await expect(viewer(page)).toBeVisible();
  await page.goto("/#composition/1/frame/1?output=2.0");
  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(/#composition\/1\/frame\/1$/);
});

test("asset generated references and history use the viewer with feedback and no final", async ({
  page,
}) => {
  const state = await workspace(page);
  const g = {
    ...structuredClone(state.runs[0].generations[0]),
    id: 9,
    variant_id: null,
    asset_id: 10,
    run_id: "asset-run",
  };
  state.assetGenerations = [g];
  state.asset.images = [
    {
      id: 9,
      hash: g.outputs[0],
      approved: true,
      source: "generated",
      lineage: { generation_id: 9, output: 0, originals: [] },
    },
  ];
  state.asset.references = state.asset.images;
  await page.goto("/#asset/10");
  const link = page.locator("a[data-output]").first();
  await link.click();
  await expect(viewer(page)).toBeVisible();
  await expect(
    viewer(page).getByRole("button", { name: /final/i }),
  ).toHaveCount(0);
  await page.keyboard.press("g");
  await expect(
    viewer(page).getByRole("button", { name: "Good G", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.keyboard.press("Escape");
  await expect(link).toBeFocused();
  await page.getByText("Past reference runs", { exact: true }).click();
  await expect(
    page
      .locator(".image-info")
      .getByRole("button", { name: "Good", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.locator(".image-info a[data-output]").click();
  await expect(viewer(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await page.goto("/#output/9/0");
  await expect(page).toHaveURL(/#asset\/10\?output=9\.0$/);
  await expect(viewer(page)).toBeVisible();
  await expect(
    viewer(page).getByRole("button", { name: /final/i }),
  ).toHaveCount(0);
});

test("retry outputs follow their model column; compare navigation keeps its focused image visible", async ({
  page,
}) => {
  const state = await workspace(page);
  viewerRun(state);
  const original = state.runs[0].generations[0];
  state.runs[0].generations.push({
    ...structuredClone(original),
    id: 4,
    retry_of: 2,
    outputs: ["synthetic-retry"],
    feedback: [{ verdict: null, asset_ratings: [], note: "" }],
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await open(page);
  await page.locator(".workspace-results a[data-output]").first().click();
  await expect(viewer(page)).toBeVisible();
  await viewer(page)
    .getByRole("button", { name: "Compare C", exact: true })
    .click();
  await viewer(page)
    .getByRole("button", { name: "Next output →", exact: true })
    .click();
  await expect(page).toHaveURL(/output=2\.1$/);
  await viewer(page)
    .getByRole("button", { name: "Next output →", exact: true })
    .click();
  await expect(page).toHaveURL(/output=4\.0$/);
  await viewer(page)
    .getByRole("button", { name: "Next output →", exact: true })
    .click();
  await expect(page).toHaveURL(/output=3\.0$/);
  await expect(
    viewer(page).getByRole("button", {
      name: "Focus Beta, output 1",
      exact: true,
    }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(viewer(page).locator(".viewer-image")).toHaveCount(3);
  await viewer(page).getByText("Technical details", { exact: true }).click();
  await expect(
    viewer(page).getByText("Prompt as sent", { exact: true }),
  ).toBeVisible();
  await expect(
    viewer(page).getByText("Request fields", { exact: true }),
  ).toBeVisible();
  await expect(
    viewer(page).getByText("Snapshot", { exact: true }),
  ).toBeVisible();
  expect(
    await viewer(page).evaluate(
      (node) => getComputedStyle(node).transitionDuration,
    ),
  ).toBe("0s");
  await page.keyboard.press("Escape");
  await expect(viewer(page).locator(".viewer-image")).toHaveCount(1);
});

test("composition asset role guidance opens on hover and focus and Escape closes it", async ({
  page,
}) => {
  const state = await workspace(page);
  state.comp.assets = [
    {
      id: 10,
      asset_id: 10,
      asset: state.asset,
      role: "the lamp",
      deselected_images: [],
      selected_originals: [],
    },
  ];
  await open(page);
  const trigger = page.getByRole("button", { name: "Help: Role", exact: true });
  await trigger.hover();
  await expect(page.getByRole("tooltip")).toContainText(
    "How this asset takes part in the image.",
  );
  await expect(trigger).toHaveAttribute(
    "aria-describedby",
    await page.getByRole("tooltip").getAttribute("id"),
  );
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await page.mouse.move(0, 0);
  await trigger.focus();
  await expect(page.getByRole("tooltip")).toBeVisible();
  await trigger.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("sequence menu has costs, modes, frame states and stop after current", async ({
  page,
}) => {
  const state = await workspace(page);
  await open(page);
  await expect(generate(page)).toBeEnabled();
  await page
    .getByRole("button", { name: "Sequence options", exact: true })
    .click();
  const menu = page.getByRole("menu", { name: "Sequence options" });
  await expect(
    menu.getByRole("menuitem", { name: /Generate the full sequence/ }),
  ).toContainText("3 frames · estimated $0.18000");
  await expect(
    menu.getByRole("menuitem", { name: /Generate the next frame/ }),
  ).toContainText("1 frame · estimated $0.06000");
  await expect(
    menu.getByRole("menuitem", { name: /Generate the rest/ }),
  ).toContainText("3 frames · estimated $0.18000");
  await menu
    .getByRole("menuitem", { name: /Generate the full sequence/ })
    .click();
  await expect.poll(() => state.sequencePosts.length).toBe(1);
  expect(state.sequencePosts[0]).toMatchObject({
    mode: "full",
    format: "16:9",
    models: [{ model: "alpha", count: 2 }],
  });
  await expect(
    page.locator(".frame-card").nth(0).getByRole("status"),
  ).toHaveText("running");
  await expect(
    page.locator(".frame-card").nth(1).getByRole("status"),
  ).toHaveText("waiting");
  await page
    .getByRole("button", { name: "Stop sequence", exact: true })
    .click();
  await expect(
    page.getByText("Sequence stops after this frame", { exact: true }),
  ).toBeVisible();
  state.comp.sequences[0].state = "stopped";
  state.comp.sequences[0].frames[0].state = "done";
  state.comp.sequences[0].frames[1].state = "stopped";
  await expect(
    page.locator(".frame-card").nth(0).getByRole("status"),
  ).toHaveText("done", { timeout: 6000 });
  await expect(
    page.locator(".frame-card").nth(1).getByRole("status"),
  ).toHaveText("stopped");
  await expect(
    page.getByRole("button", { name: "Stop sequence", exact: true }),
  ).toHaveCount(0);
});

test("inspector previous thumbnail and switch, prompt legend and missing-image notice", async ({
  page,
}) => {
  const previous = {
    hash: "synthetic-previous",
    role: "previous frame",
    asset_id: null,
    asset_name: "the previous frame",
    type: "other",
    frame_id: 1,
    generation_id: 2,
    output: 0,
    source: "first output",
  };
  const state = await workspace(page, { references: [previous] });
  await page.goto("/#composition/1/frame/2");
  await expect(generate(page)).toBeEnabled();
  await expect(
    page.getByRole("img", { name: "Previous frame reference", exact: true }),
  ).toHaveAttribute("src", "/api/files/synthetic-previous");
  const toggle = page.getByRole("checkbox", { name: "Use the previous frame" });
  await expect(toggle).toBeChecked();
  await page.getByRole("button", { name: /View prompts/ }).click();
  await expect(
    page.getByRole("dialog", { name: "View prompts" }),
  ).toContainText("Image 1: the previous frame · previous frame");
  await page.getByRole("button", { name: "Close prompts" }).click();
  await toggle.click();
  await expect(toggle).not.toBeChecked();
  await expect
    .poll(() => state.comp.variants[1].use_previous_frame)
    .toBe(false);
  await expect(page.locator(".reference-total")).toHaveText(
    "0 references selected",
  );
  state.references = [];
  await toggle.click();
  await expect(toggle).toBeChecked();
  await expect(
    page.getByText(
      "No previous-frame image is available; this frame will run without it.",
    ),
  ).toBeVisible();
  await page.goto("/#composition/1/frame/1");
  await expect(
    page.getByRole("checkbox", { name: "Use the previous frame" }),
  ).toHaveCount(0);
});
