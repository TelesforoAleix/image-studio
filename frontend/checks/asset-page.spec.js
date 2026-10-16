import { test, expect } from "@playwright/test";

async function assetPage(page) {
  const original = {
    id: 1,
    hash: "synthetic-original",
    source: "uploaded",
    approved: false,
    rejected: false,
    width: 100,
    height: 100,
  };
  const image = (id) => ({
    ...original,
    id,
    hash: `synthetic-${id}`,
    source: "generated",
    lineage: {
      generation_id: id,
      output: 0,
      originals: [{ hash: original.hash }],
    },
  });
  const state = {
    asset: {
      id: 1,
      name: "Synthetic asset",
      type: "other",
      type_tag: "",
      description: "",
      preserve: "",
      images: [original, image(2), image(3), { ...image(4), approved: true }],
    },
    patches: [],
    uploads: [],
    runs: [],
    posts: [],
    holdUpload: null,
    failSave: false,
    failReviewId: null,
  };
  const info = {
    display_name: "Synthetic model",
    max_references: 10,
    seconds_per_image: 5,
    aspect_ratios: { values: ["1:1"] },
    qualities: { values: ["standard"] },
    price_per_image: { standard: 0.1 },
  };
  const generation = (id, status = "done", count = 1) => ({
    id,
    model: "synthetic",
    model_info: info,
    asset_id: 1,
    state: status,
    count,
    outputs: status === "done" ? [`synthetic-${id}`] : [],
    references: [
      {
        hash: original.hash,
        asset_id: 1,
        asset_name: "Synthetic asset",
        role: "original",
      },
    ],
    feedback: [],
    created_at: new Date().toISOString(),
  });
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname.slice(4),
      method = req.method();
    let value;
    if (path === "/projects") value = [];
    else if (path === "/spend") value = { estimated_spend: 0 };
    else if (path === "/models")
      value = [{ model_name: "synthetic", model_info: info }];
    else if (path === "/render")
      value = [
        {
          model: "synthetic",
          rendered_prompt: "Synthetic content",
          estimated_cost: req.postDataJSON().models[0].count * 0.1,
          references: [],
        },
      ];
    else if (path === "/assets/1/reference-preview")
      value = {
        prompt: "Synthetic content",
        references: [{ hash: original.hash }],
      };
    else if (path === "/assets/1/generations") {
      if (method === "POST") {
        const body = req.postDataJSON();
        state.posts.push(body);
        state.runs.unshift(generation(5, "waiting", body.count));
      }
      value = state.runs;
    } else if (/^\/generations\/\d+$/.test(path))
      value = generation(Number(path.split("/")[2]));
    else if (path.startsWith("/files/"))
      return route.fulfill({
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="olive"/></svg>',
      });
    else if (path === "/assets/1/images" && method === "POST") {
      state.uploads.push(req.postDataBuffer().toString());
      if (state.holdUpload) await state.holdUpload;
      value = read();
    } else if (/^\/assets\/1\/images\/\d+$/.test(path)) {
      const id = Number(path.split("/").at(-1));
      const body = req.postDataJSON();
      if (state.failReviewId === id)
        return route.fulfill({
          status: 400,
          json: { error: "Synthetic review failed" },
        });
      state.patches.push({ id, body });
      Object.assign(
        state.asset.images.find((i) => i.id === id),
        body,
      );
      value = read();
    } else if (path === "/assets/1") {
      if (method === "PATCH") {
        if (state.failSave)
          return route.fulfill({
            status: 400,
            json: { error: "Synthetic save failure" },
          });
        Object.assign(state.asset, req.postDataJSON());
      }
      value = read();
    } else throw new Error(`Unexpected request ${method} ${path}`);
    await route.fulfill({ json: value });
  });
  function read() {
    return {
      ...state.asset,
      originals: state.asset.images.filter((i) => i.source === "uploaded"),
      references: state.asset.images.filter((i) => i.approved && !i.rejected),
    };
  }
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.goto("/#asset/1");
  await expect(
    page.getByRole("heading", { name: "Images", exact: true }),
  ).toBeVisible();
  return state;
}
const region = (page, name) => page.getByRole("region", { name, exact: true });

test("images precede the inspector; focused candidates support A/R and confirmed bulk review", async ({
  page,
}) => {
  const state = await assetPage(page);
  const sections = page.locator(".asset-main > section");
  expect(
    await sections.evaluateAll((nodes) =>
      nodes.slice(0, 3).map((n) => n.getAttribute("aria-label")),
    ),
  ).toEqual(["To review", "References", "Originals"]);
  const images = await region(page, "To review").boundingBox(),
    inspector = await page
      .getByRole("complementary", { name: "Asset inspector" })
      .boundingBox();
  expect(inspector.x).toBeGreaterThan(images.x + images.width);
  expect(inspector.y).toBeLessThan(images.y);
  await expect(page.getByRole("button", { name: "Save asset" })).toHaveCount(0);
  await page.getByRole("article", { name: "Candidate 2", exact: true }).focus();
  await page.keyboard.press("a");
  await expect
    .poll(() => state.patches)
    .toEqual([{ id: 2, body: { approved: true } }]);
  await expect(
    region(page, "To review").getByRole("article", {
      name: "Candidate 2",
      exact: true,
    }),
  ).toHaveCount(0);
  await page.getByRole("article", { name: "Candidate 3", exact: true }).focus();
  await page.keyboard.press("r");
  await expect.poll(() => state.patches.length).toBe(2);
  expect(state.patches[1]).toEqual({ id: 3, body: { rejected: true } });
  await expect(region(page, "To review")).toHaveCount(0);
  await page.getByRole("checkbox", { name: "Show rejected" }).check();
  await expect(region(page, "Rejected").getByRole("article")).toHaveCount(1);
});

test("Approve all waits for inline confirmation then approves every candidate", async ({
  page,
}) => {
  const state = await assetPage(page);
  await page.getByRole("button", { name: "Approve all", exact: true }).click();
  expect(state.patches).toHaveLength(0);
  await page.getByRole("button", { name: "Yes, approve all" }).click();
  await expect.poll(() => state.patches.length).toBe(2);
  expect(state.patches).toEqual([
    { id: 2, body: { approved: true } },
    { id: 3, body: { approved: true } },
  ]);
});

test("drop uploads two files with individual progress and refuses type and size per file", async ({
  page,
}) => {
  const state = await assetPage(page);
  let release;
  state.holdUpload = new Promise((resolve) => {
    release = resolve;
  });
  const dataTransfer = await page.evaluateHandle(() => {
    const dt = new DataTransfer();
    for (const name of ["first.png", "second.png"])
      dt.items.add(
        new File([new Uint8Array([137, 80, 78, 71])], name, {
          type: "image/png",
        }),
      );
    dt.items.add(new File(["synthetic"], "wrong.txt", { type: "text/plain" }));
    dt.items.add(
      new File([new Uint8Array(26 * 1024 * 1024)], "large.png", {
        type: "image/png",
      }),
    );
    return dt;
  });
  await region(page, "Originals").dispatchEvent("drop", { dataTransfer });
  await expect(page.getByRole("progressbar")).toHaveCount(2);
  await expect(
    page.getByRole("alert").filter({ hasText: "Choose JPEG" }),
  ).toBeVisible();
  await expect(
    page.getByRole("alert").filter({ hasText: "Maximum size" }),
  ).toBeVisible();
  state.holdUpload = null;
  release();
  await expect.poll(() => state.uploads.length).toBe(2);
  expect(state.uploads[0]).toContain('filename="first.png"');
  expect(state.uploads[1]).toContain('filename="second.png"');
  await expect(
    page.getByRole("status").filter({ hasText: /^Uploaded$/ }),
  ).toHaveCount(2);
});

test("inspector autosaves all fields, retains help, and flushes before leaving", async ({
  page,
}) => {
  const state = await assetPage(page);
  for (const [label, key] of [
    [/^Name/, "name"],
    [/^Label/, "type_tag"],
    ["Description", "description"],
    ["What must stay the same", "preserve"],
  ]) {
    await page.getByRole("textbox", { name: label }).fill(`Synthetic ${key}`);
    await expect.poll(() => state.asset[key]).toBe(`Synthetic ${key}`);
  }
  await page.getByRole("combobox", { name: /^Type/ }).selectOption("person");
  await expect.poll(() => state.asset.type).toBe("person");
  for (const label of ["Description", "What must stay the same"]) {
    const help = page.getByRole("button", {
      name: `Help: ${label}`,
      exact: true,
    });
    await help.hover();
    await expect(page.getByRole("tooltip")).toBeVisible();
    await help.press("Escape");
    await page.mouse.move(0, 0);
    await help.blur();
    await help.focus();
    await expect(page.getByRole("tooltip")).toBeVisible();
    await help.press("Escape");
  }
  state.failSave = true;
  await page
    .getByRole("textbox", { name: "Description", exact: true })
    .fill("Synthetic unsaved");
  await expect(
    page.getByRole("status").filter({ hasText: "Synthetic save failure" }),
  ).toBeVisible();
  await page.locator(".breadcrumb a").first().click();
  await expect(page).toHaveURL(/#asset\/1$/);
  state.failSave = false;
  await page.getByRole("button", { name: "Generate reference views" }).click();
  expect(state.asset.description).toBe("Synthetic unsaved");
});

test("generation sheet estimates cost, queues and displays placeholder tiles which fill in", async ({
  page,
}) => {
  const state = await assetPage(page);
  await expect(page.locator("button.primary")).toHaveCount(1);
  await page.getByRole("button", { name: "Generate reference views" }).click();
  const sheet = page.getByRole("dialog", {
    name: "Generate reference views",
    exact: true,
  });
  await sheet
    .getByRole("checkbox", { name: "Synthetic model", exact: true })
    .check();
  await sheet
    .getByRole("combobox", { name: "Outputs", exact: true })
    .selectOption("2");
  await expect(
    sheet.getByText("Estimated run cost: $0.20000", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("button.primary")).toHaveCount(1);
  await sheet.getByRole("button", { name: "Generate", exact: true }).click();
  await expect(sheet).toHaveCount(0);
  expect(state.posts[0]).toMatchObject({ model: "synthetic", count: 2 });
  await expect(
    region(page, "To review").getByRole("article", {
      name: "Generating reference",
      exact: true,
    }),
  ).toHaveCount(2);
  state.runs[0].state = "done";
  state.runs[0].outputs = ["synthetic-5", "synthetic-6"];
  state.asset.images.push({
    ...state.asset.images[1],
    id: 5,
    hash: "synthetic-5",
  });
  await expect(
    region(page, "To review").getByRole("article", {
      name: "Generating reference",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("article", { name: "Candidate 5", exact: true }),
  ).toBeVisible();
});

test("viewer footer holds lineage, originals use viewer, and toolbar menus support keyboard", async ({
  page,
}) => {
  await assetPage(page);
  await expect(region(page, "References").locator(".lineage")).toHaveCount(0);
  await region(page, "References").locator("a[data-output]").click();
  const viewer = page.getByRole("dialog", { name: "Output viewer" });
  await expect(viewer.locator(".viewer-footer .lineage img")).toHaveAttribute(
    "src",
    "/api/files/synthetic-original",
  );
  await expect(viewer.getByRole("button", { name: /final/i })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await region(page, "Originals").locator("a[data-output]").click();
  await expect(viewer.locator(".viewer-image img")).toHaveAttribute(
    "src",
    "/api/files/synthetic-original",
  );
  await expect(viewer.getByRole("button", { name: /feedback/i })).toHaveCount(
    0,
  );
  await page.keyboard.press("Escape");
  await page.goto("/#asset/1?output=0.1");
  await expect(viewer.locator(".viewer-image img")).toHaveAttribute(
    "src",
    "/api/files/synthetic-original",
  );
  await expect(
    viewer.getByRole("button", { name: "↑ Previous run", exact: true }),
  ).toBeDisabled();
  await page.keyboard.press("Escape");
  const share = page.getByRole("button", { name: "Share", exact: true });
  await share.focus();
  await page.keyboard.press("ArrowDown");
  await expect(
    page.getByRole("menuitem", { name: "Export asset" }),
  ).toBeFocused();
  await expect(
    page.getByRole("menuitem", { name: "Export asset" }),
  ).toHaveAttribute("href", "/api/assets/1/export.zip");
  await page.keyboard.press("Escape");
  await expect(share).toBeFocused();
  const more = page.getByRole("button", { name: "⋯", exact: true });
  await more.focus();
  await page.keyboard.press("ArrowDown");
  await expect(
    page.getByRole("menuitem", { name: "Duplicate asset" }),
  ).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("button", { name: "Yes, delete asset" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.locator("button.primary")).toHaveCount(1);
});

test("Reject all confirms and partial bulk errors retain remaining candidates", async ({
  page,
}) => {
  const state = await assetPage(page);
  state.failReviewId = 3;
  await page.getByRole("button", { name: "Reject all", exact: true }).click();
  expect(state.patches).toHaveLength(0);
  await page.getByRole("button", { name: "Yes, reject all" }).click();
  await expect(page.getByRole("alert")).toHaveText("Synthetic review failed");
  await expect(region(page, "To review").getByRole("article")).toHaveCount(1);
  expect(state.patches).toEqual([{ id: 2, body: { rejected: true } }]);
  state.failReviewId = null;
  await page.getByRole("button", { name: "Yes, reject all" }).click();
  await expect(region(page, "To review")).toHaveCount(0);
  await expect(
    page.getByRole("status").filter({ hasText: "Candidates rejected." }),
  ).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "Candidates rejected." }),
  ).toHaveCount(0, { timeout: 6000 });
});
