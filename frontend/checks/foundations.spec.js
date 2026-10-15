import { test, expect } from "@playwright/test";

const info = {
  display_name: "Synthetic model",
  placeholder: true,
  seconds_per_image: 10,
  max_references: 4,
  aspect_ratios: { values: ["1:1"] },
  qualities: { values: ["standard"] },
  price_per_image: { standard: 0 },
};
const feedback = {
  verdict: null,
  asset_ratings: [],
  note: "",
  updated_at: null,
};
const generation = (state = "done") => ({
  id: 1,
  variant_id: 1,
  model: "synthetic",
  model_info: info,
  state,
  count: 2,
  outputs: state === "done" ? ["synthetic-output"] : [],
  references: [],
  feedback: state === "done" ? [feedback] : [],
  started_at: new Date(Date.now() - 5000).toISOString(),
  created_at: new Date().toISOString(),
});
async function mock(page, initial = "done") {
  const state = {
    status: initial,
    polls: 0,
    queued: 0,
    fail: false,
    hold: null,
    pollHold: null,
    storyboard: false,
    unknownTime: false,
    references: false,
  };
  const project = { id: 1, name: "Synthetic project", instructions: "" };
  const asset = {
    id: 1,
    name: "Synthetic asset",
    type: "other",
    description: "",
    preserve: "",
    images: [],
    references: [],
    originals: [],
  };
  const frame = {
    id: 1,
    name: "Frame 1",
    instructions: "",
    deselected_images: [],
    selected_originals: [],
  };
  const comp = {
    id: 1,
    name: "Synthetic composition",
    kind: "single",
    brief: "",
    assets: [],
    variants: [frame],
  };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.slice(4);
    const method = route.request().method();
    let value;
    if (path === "/projects") value = [project];
    else if (path === "/projects/1") value = project;
    else if (path.startsWith("/assets?")) value = [];
    else if (path === "/assets") value = [];
    else if (path === "/assets/1/reference-preview")
      value = { prompt: "Synthetic content", references: [] };
    else if (path === "/assets/1/generations") {
      if (method === "POST") {
        state.queued++;
        state.status = "waiting";
      } else state.polls++;
      value = [generation(state.status)];
    } else if (path === "/assets/1") {
      if (state.hold && method === "PATCH") await state.hold;
      if (state.fail && method === "PATCH")
        return route.fulfill({
          status: 400,
          json: { error: "Synthetic save failure" },
        });
      value = asset;
    } else if (path === "/compositions/1")
      value = { ...comp, kind: state.storyboard ? "storyboard" : "single" };
    else if (path === "/compositions" || path === "/projects/1/compositions")
      value = [];
    else if (path === "/models")
      value = [{ model_name: "synthetic", model_info: info }];
    else if (path === "/variants/1") value = { ...frame, composition_id: 1 };
    else if (path === "/variants/1/preview")
      value = { prompt: "Synthetic content", references: [] };
    else if (path === "/render")
      value = [
        {
          model: "synthetic",
          rendered_prompt: "Synthetic content",
          references: [],
          estimated_cost: 0,
        },
      ];
    else if (path === "/spend") value = { estimated_spend: 0 };
    else if (path === "/variants/1/runs") {
      if (method === "POST") {
        state.queued++;
        state.status = "waiting";
      } else {
        state.polls++;
        if (state.pollHold) await state.pollHold;
      }
      value = {
        run_id: "synthetic-run",
        created_at: new Date().toISOString(),
        references: [],
        generations: [
          {
            ...generation(state.status),
            model_info: state.unknownTime
              ? { ...info, seconds_per_image: null }
              : info,
          },
        ],
      };
      if (method === "GET") value = [value];
    } else if (path === "/generations/1/retry") {
      state.queued++;
      state.status = "waiting";
      value = { ...generation("waiting"), id: 2, retry_of: 1 };
    } else if (path === "/variants/1/final") value = null;
    else if (path === "/generations/1")
      value = state.references
        ? { ...generation(), variant_id: null, asset_id: 1 }
        : generation();
    else if (path === "/storage")
      value = Object.fromEntries(
        ["total", "uploaded", "generated", "placeholder"].map((k) => [
          k,
          { bytes: 0, file_count: 0 },
        ]),
      );
    else if (path.startsWith("/files/")) return route.fulfill({ status: 204 });
    else throw new Error(`Unexpected synthetic request: ${method} ${path}`);
    await route.fulfill({ json: value });
  });
  return state;
}

for (const theme of ["light", "dark"]) {
  test(`${theme}: token contrast and exactly one primary per route`, async ({
    page,
  }) => {
    const state = await mock(page);
    await page.emulateMedia({ colorScheme: theme });
    await page.goto("/#assets");
    const ratios = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement);
      const get = (name) => style.getPropertyValue(`--${name}`).trim();
      const luminance = (hex) => {
        const rgb = hex
          .slice(1)
          .match(/../g)
          .map((v) => parseInt(v, 16) / 255)
          .map((v) =>
            v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4,
          );
        return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
      };
      const ratio = (a, b) => {
        const x = luminance(get(a)),
          y = luminance(get(b));
        return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
      };
      return Object.fromEntries([
        ...["canvas", "panel", "raised"].flatMap((surface) =>
          [
            "text",
            "secondary-text",
            "success",
            "warning",
            "danger",
            "accent",
            "border",
            "focus",
          ].map((color) => [`${color}/${surface}`, ratio(color, surface)]),
        ),
        ["on-accent/accent", ratio("on-accent", "accent")],
      ]);
    });
    for (const [pair, ratio] of Object.entries(ratios))
      expect(ratio, `${theme} ${pair}`).toBeGreaterThanOrEqual(
        /^(border|focus)/.test(pair) ? 3 : 4.5,
      );
    console.log(
      `CONTRAST ${theme}: ${Object.entries(ratios)
        .map(([k, v]) => `${k}=${v.toFixed(2)}:1`)
        .join(", ")}`,
    );
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const route of [
      "assets",
      "assets?used_by_project=1",
      "asset/1",
      "compositions",
      "projects",
      "project/1",
      "storage",
      "composition/1/frame/1/setup",
      "composition/1/frame/1/generate",
      "composition/1/frame/1/history",
      "output/1/0",
      "library",
      "frame/1",
      "composition/1",
    ]) {
      await page.goto(`/#${route}`);
      if (route.startsWith("output/"))
        await expect(
          page.getByRole("dialog", { name: "Output viewer" }),
        ).toBeVisible();
      await expect(
        page.getByRole("button").and(page.locator("button.primary")),
      ).toHaveCount(1);
    }
    await page.goto("/#output/1/0");
    await page
      .getByRole("dialog", { name: "Output viewer" })
      .getByRole("button", { name: "Provide feedback Enter", exact: true })
      .click();
    await expect(
      page.getByRole("button").and(page.locator("button.primary")),
    ).toHaveCount(1);
    for (const route of ["assets", "compositions"]) {
      await page.goto(`/#${route}`);
      await page
        .getByRole("button", {
          name: route === "assets" ? "New asset" : "New composition",
        })
        .click();
      await expect(
        page.getByRole("button").and(page.locator("button.primary")),
      ).toHaveCount(1);
    }
    state.storyboard = true;
    for (const tab of ["setup", "generate", "history"]) {
      await page.goto(`/#composition/1/frame/1/${tab}`);
      await expect(
        page.getByRole("button").and(page.locator("button.primary")),
      ).toHaveCount(1);
    }
    state.references = true;
    await page.goto("/#output/1/0");
    await expect(
      page.getByRole("button").and(page.locator("button.primary")),
    ).toHaveCount(1);
    expect(errors).toEqual([]);
    console.log(
      `PRIMARY ${theme}: all routes, create forms and feedback form exactly one`,
    );
  });
}

test("polling never disables controls, stops idle, resumes on retry", async ({
  page,
}) => {
  const state = await mock(page, "running");
  await page.clock.install();
  await page.goto("/#composition/1/frame/1/history");
  await expect(page.getByText(/s elapsed/)).toBeVisible();
  await expect(page.getByText(/about \d+ s left/)).toBeVisible();
  await expect.poll(() => state.polls).toBeGreaterThanOrEqual(2);
  const before = state.polls;
  let releasePoll;
  state.pollHold = new Promise((resolve) => {
    releasePoll = resolve;
  });
  await page.clock.fastForward(3000);
  await expect.poll(() => state.polls).toBeGreaterThan(before);
  await expect(
    page.locator(
      "button:disabled, input:disabled, select:disabled, textarea:disabled",
    ),
  ).toHaveCount(0);
  state.status = "failed";
  state.pollHold = null;
  releasePoll();
  await page.clock.fastForward(3000);
  await expect(
    page.getByRole("button", { name: "Retry", exact: true }),
  ).toBeVisible();
  await page.waitForTimeout(50);
  const idle = state.polls;
  await page.clock.fastForward(12000);
  expect(state.polls).toBe(idle);
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect.poll(() => state.queued).toBe(1);
  await expect(
    page.getByText("Waiting for the image service", { exact: false }),
  ).toBeVisible();
  const resumed = state.polls;
  await page.clock.fastForward(3000);
  await expect.poll(() => state.polls).toBeGreaterThan(resumed);
  state.status = "done";
  await page.clock.fastForward(3000);
  await expect(page.getByRole("button", { name: "Mark final" })).toBeVisible();
  await page.waitForTimeout(50);
  const done = state.polls;
  await page.clock.fastForward(12000);
  expect(state.polls).toBe(done);
  console.log(
    "POLLING: controls enabled during polls; failed/done stop; retry resumes",
  );
});

test("queueing starts run polling and reference history also stops idle", async ({
  page,
}) => {
  const state = await mock(page);
  await page.clock.install();
  await page.goto("/#composition/1/frame/1/generate");
  await page.getByText("+ model", { exact: true }).click();
  await page
    .getByRole("checkbox", { name: "Synthetic model", exact: true })
    .check();
  await page.getByText("+ model", { exact: true }).click();
  await page.clock.fastForward(300);
  await expect(
    page.getByRole("button", { name: "Generate", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Generate", exact: true }).click();
  await expect.poll(() => state.queued).toBe(1);
  await expect(page.getByText(/Waiting for the image service/)).toBeVisible();
  await page.waitForTimeout(50);
  const before = state.polls;
  await page.clock.fastForward(3000);
  await expect.poll(() => state.polls).toBeGreaterThan(before);
  state.status = "done";
  await page.goto("/#asset/1");
  await expect(page.getByText("done · 1/2")).toBeVisible();
  await page.waitForTimeout(50);
  const idle = state.polls;
  await page.clock.fastForward(12000);
  expect(state.polls).toBe(idle);
  await page
    .getByRole("checkbox", { name: "Synthetic model", exact: true })
    .check();
  await page.clock.fastForward(300);
  await page
    .getByRole("button", { name: "Generate reference views", exact: true })
    .click();
  await expect.poll(() => state.queued).toBe(2);
  await expect(page.getByText(/Waiting for the image service/)).toBeVisible();
  console.log("QUEUE: frame and reference-view queueing restart idle polling");
});

test("actions disable only their conflicting form, report errors locally and dismiss success", async ({
  page,
}) => {
  const state = await mock(page);
  await page.clock.install();
  await page.goto("/#asset/1");
  let release;
  state.hold = new Promise((resolve) => {
    release = resolve;
  });
  await page.getByRole("button", { name: "Save asset", exact: true }).click();
  await expect(page.getByRole("button", { name: /Save asset/ })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Upload selected images" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Duplicate asset" }),
  ).toBeEnabled();
  state.fail = true;
  release();
  await expect(page.getByRole("alert")).toHaveText("Synthetic save failure");
  await expect(
    page
      .getByRole("button", { name: "Save asset" })
      .locator("..")
      .getByRole("alert"),
  ).toBeVisible();
  state.fail = false;
  state.hold = null;
  await page.getByRole("button", { name: "Save asset", exact: true }).click();
  await expect(page.getByText("Asset saved.", { exact: true })).toBeVisible();
  await page.clock.fastForward(4100);
  await expect(page.getByText("Asset saved.", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
  console.log(
    "ACTIONS: local pending, local error, announced auto-dismissed confirmation",
  );
});

test("running progress falls back to elapsed time without a profile estimate", async ({
  page,
}) => {
  const state = await mock(page, "running");
  state.unknownTime = true;
  await page.clock.install();
  await page.goto("/#composition/1/frame/1/history");
  await expect(page.getByText(/s elapsed/)).toBeVisible();
  await expect(page.getByText(/s left/)).toHaveCount(0);
  console.log("PROGRESS: elapsed time alone when seconds_per_image is missing");
});

async function proveHelp(page, label, copy) {
  const trigger = page.getByRole("button", {
    name: `Help: ${label}`,
    exact: true,
  });
  await trigger.hover();
  let tooltip = page.getByRole("tooltip");
  await expect(tooltip).toBeVisible();
  await expect(tooltip).toContainText(copy);
  await expect(trigger).toHaveAttribute(
    "aria-describedby",
    await tooltip.getAttribute("id"),
  );
  await page.keyboard.press("Escape");
  await expect(tooltip).toHaveCount(0);
  await page.mouse.move(0, 0);
  await trigger.focus();
  await expect(tooltip).toBeVisible();
  await expect(tooltip).toContainText(copy);
  await trigger.press("Escape");
  await expect(tooltip).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await trigger.blur();
}

test("single and storyboard fields and every guidance tooltip support hover, focus and Escape", async ({
  page,
}) => {
  const state = await mock(page);
  await page.goto("/#composition/1/frame/1");
  await expect(
    page.getByRole("textbox", { name: "Brief", exact: true }),
  ).toBeVisible();
  for (const name of [
    "Direction",
    "Scene",
    "Frame name",
    "Frame instructions",
    "What happens in this frame",
  ])
    await expect(page.getByRole("textbox", { name, exact: true })).toHaveCount(
      0,
    );
  await proveHelp(
    page,
    "Brief",
    "What this image shows and how it should feel",
  );
  await page.getByText("Style · None", { exact: true }).click();
  await proveHelp(
    page,
    "Style",
    "The project's style applies unless this composition picks its own.",
  );
  state.storyboard = true;
  await page.goto("/#assets");
  await page.goto("/#composition/1/frame/1");
  await expect(
    page.getByRole("textbox", { name: "Brief", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Frame name", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", {
      name: "What happens in this frame",
      exact: true,
    }),
  ).toBeVisible();
  await proveHelp(page, "Brief", "The story as a whole");
  await proveHelp(
    page,
    "What happens in this frame",
    "Don't repeat the brief.",
  );
  await page.goto("/#projects");
  await proveHelp(
    page,
    "Creative direction",
    "How every image in this project should look and feel",
  );
  await page.goto("/#asset/1");
  await proveHelp(page, "Description", "What the asset is, in plain words");
  await proveHelp(
    page,
    "What must stay the same",
    "The features a model must not change",
  );
});
