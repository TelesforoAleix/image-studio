import { test, expect } from "@playwright/test";

async function navigation(page) {
  const state = {
    projects: [
      {
        id: 1,
        name: "Synthetic editorial",
        instructions: "Warm window light",
        style_asset_id: 3,
      },
    ],
    assets: [
      {
        id: 1,
        name: "Library lamp",
        type: "object_vehicle",
        thumbnail: "lamp",
      },
      { id: 2, name: "Project person", type: "person", thumbnail: "person" },
      { id: 3, name: "Warm style", type: "style", thumbnail: "style" },
      {
        id: 4,
        name: "Retained chair",
        type: "other",
        thumbnail: null,
        deleted_at: "2026-10-01T00:00:00Z",
      },
    ],
    members: { 1: [2, 3, 4] },
    comps: [
      {
        id: 1,
        name: "Editorial opening",
        project_id: 1,
        kind: "storyboard",
        thumbnail: "final",
        frame_count: 2,
        last_activity: "2026-10-15T12:00:00Z",
      },
      {
        id: 2,
        name: "Standalone detail",
        project_id: null,
        kind: "single",
        thumbnail: "latest",
        frame_count: 1,
        last_activity: "2026-10-14T12:00:00Z",
      },
      {
        id: 3,
        name: "Empty study",
        project_id: null,
        kind: "single",
        thumbnail: null,
        frame_count: 1,
        last_activity: "2026-10-13T12:00:00Z",
      },
    ],
    packs: {},
    posts: [],
    fail: false,
  };
  const detail = (c) => ({
    ...c,
    brief: "",
    assets: state.packs[c.id] || [],
    style: null,
    style_deselected_images: [],
    variants: Array.from({ length: c.frame_count }, (_, i) => ({
      id: c.id * 10 + i,
      name: `Frame ${i + 1}`,
      instructions: "",
      deselected_images: [],
      selected_originals: [],
      final: null,
    })),
  });
  const asset = (a) => ({
    ...a,
    description: "",
    preserve: "",
    images: a.thumbnail
      ? [{ id: a.id, hash: a.thumbnail, source: "uploaded", approved: true }]
      : [],
    references: [],
    originals: [],
  });
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url()),
      path = url.pathname.slice(4),
      method = req.method();
    let value;
    if (path === "/projects") {
      if (method === "POST") {
        const p = { id: state.projects.length + 1, ...req.postDataJSON() };
        state.projects.push(p);
        state.members[p.id] = [];
        value = p;
      } else value = state.projects;
    } else if (/^\/projects\/\d+$/.test(path)) {
      value = state.projects.find((p) => p.id === Number(path.split("/")[2]));
      if (method === "PATCH") {
        if (state.fail)
          return route.fulfill({
            status: 400,
            json: { error: "Synthetic save failure" },
          });
        Object.assign(value, req.postDataJSON());
      }
    } else if (/^\/projects\/\d+\/assets(?:\/\d+)?$/.test(path)) {
      const [, , project, , id] = path.split("/");
      if (method === "PUT")
        state.members[project] = [
          ...new Set([...state.members[project], Number(id)]),
        ];
      if (method === "DELETE")
        state.members[project] = state.members[project].filter(
          (i) => i !== Number(id),
        );
      value =
        method === "GET"
          ? state.assets.filter((a) => state.members[project].includes(a.id))
          : { saved: true };
    } else if (path === "/assets")
      value = state.assets.filter(
        (a) =>
          !a.deleted_at &&
          (!url.searchParams.get("type") ||
            a.type === url.searchParams.get("type")),
      );
    else if (/^\/assets\/\d+$/.test(path))
      value = asset(
        state.assets.find((a) => a.id === Number(path.split("/")[2])),
      );
    else if (path === "/compositions") {
      if (method === "POST") {
        const c = {
          ...state.comps[2],
          id: state.comps.length + 1,
          ...req.postDataJSON(),
        };
        state.posts.push(req.postDataJSON());
        state.comps.push(c);
        value = detail(c);
      } else
        value = state.comps.filter(
          (c) =>
            !url.searchParams.has("project_id") ||
            (url.searchParams.get("project_id") === "none"
              ? c.project_id === null
              : c.project_id === Number(url.searchParams.get("project_id"))),
        );
    } else if (/^\/compositions\/\d+$/.test(path))
      value = detail(
        state.comps.find((c) => c.id === Number(path.split("/")[2])),
      );
    else if (/^\/compositions\/\d+\/assets\/\d+$/.test(path)) {
      const [, , compId, , assetId] = path.split("/");
      const c = state.comps.find((c) => c.id === Number(compId));
      const a = state.assets.find((a) => a.id === Number(assetId));
      state.packs[compId] = [
        {
          id: a.id,
          asset_id: a.id,
          asset: asset(a),
          role: a.name,
          deselected_images: [],
          selected_originals: [],
        },
      ];
      if (c.project_id)
        state.members[c.project_id] = [
          ...new Set([...state.members[c.project_id], a.id]),
        ];
      value = detail(c);
    } else if (path === "/models") value = [];
    else if (path === "/spend") value = { estimated_spend: 0.12 };
    else if (path.endsWith("/runs")) value = [];
    else if (/^\/variants\/\d+\/final$/.test(path)) value = null;
    else if (path.endsWith("/preview")) value = { prompt: "", references: [] };
    else if (path.startsWith("/files/"))
      return route.fulfill({
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="180"><rect width="240" height="180" fill="olive"/></svg>',
      });
    else throw new Error(`Unexpected synthetic request: ${method} ${path}`);
    return route.fulfill({ json: value });
  });
  return state;
}
const sidebar = (page) => page.getByRole("complementary", { name: "Sidebar" });
const sheet = (page, name) => page.getByRole("dialog", { name, exact: true });

test("sidebar projects/types/current, Studio and Assets image grids and name searches", async ({
  page,
}) => {
  await navigation(page);
  await page.goto("/#studio");
  await expect(
    sidebar(page).getByRole("link", { name: "All compositions", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  for (const name of [
    "No project",
    "Synthetic editorial",
    "All assets",
    "People",
    "Garments/Products",
    "Objects/Vehicles",
    "Environments",
    "Styles",
    "Other",
    "Storage",
  ])
    await expect(
      sidebar(page).getByRole("link", { name, exact: true }),
    ).toBeVisible();
  await expect(sidebar(page)).toContainText("$0.12");
  await expect(page.locator(".composition-grid .image-tile")).toHaveCount(3);
  await expect(
    page.locator(".composition-grid .tile-image").first(),
  ).toHaveAttribute("src", "/api/files/final");
  await expect(
    page.locator(".composition-grid .tile-image").nth(1),
  ).toHaveAttribute("src", "/api/files/latest");
  await expect(page.locator(".composition-grid .tile-image").last()).toHaveText(
    "No output yet",
  );
  await expect(page.locator(".composition-grid")).toContainText("2 frames");
  await page
    .getByRole("searchbox", { name: "Search compositions" })
    .fill("DETAIL");
  await expect(page.locator(".composition-grid .image-tile")).toHaveCount(1);
  await sidebar(page)
    .getByRole("link", { name: "No project", exact: true })
    .click();
  await expect(page.locator(".composition-grid .image-tile")).toHaveCount(2);
  await sidebar(page)
    .getByRole("link", { name: "All assets", exact: true })
    .click();
  await expect(page.locator(".asset-grid .image-tile")).toHaveCount(3);
  await expect(page.locator(".asset-grid img")).toHaveCount(3);
  await page.getByRole("searchbox", { name: "Search assets" }).fill("LAMP");
  await expect(page.locator(".asset-grid .image-tile")).toHaveCount(1);
  await page.getByRole("searchbox", { name: "Search assets" }).fill("absent");
  await expect(
    page.getByRole("heading", { name: "No matching assets" }),
  ).toBeVisible();
  await sidebar(page)
    .getByRole("link", { name: "People", exact: true })
    .click();
  await expect(
    sidebar(page).getByRole("link", { name: "People", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(page.locator(".asset-grid .image-tile")).toHaveCount(1);
  await expect(page.locator(".asset-grid")).toContainText("Project person");
  await page.getByRole("button", { name: "New asset", exact: true }).click();
  await expect(sheet(page, "New asset")).toBeVisible();
  await expect(
    sheet(page, "New asset").getByRole("button", {
      name: "Create asset",
      exact: true,
    }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sheet(page, "New asset")).toHaveCount(0);
});

test("New project buttons open a small form and creation opens its read view", async ({
  page,
}) => {
  const state = await navigation(page);
  await page.goto("/#studio");
  await expect(
    page.getByRole("textbox", { name: "Name", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "New project", exact: true }).click();
  await expect(sheet(page, "New project")).toBeVisible();
  await sheet(page, "New project")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await sidebar(page)
    .getByRole("button", { name: "+ New project", exact: true })
    .click();
  await sheet(page, "New project")
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("Synthetic new folder");
  await sheet(page, "New project")
    .getByRole("button", { name: "Create project", exact: true })
    .click();
  await expect(page).toHaveURL(/#studio\/project\/2$/);
  await expect(
    page.getByRole("heading", { name: "Synthetic new folder", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "Creative direction", exact: true }),
  ).toHaveCount(0);
  await expect(
    sidebar(page).getByRole("link", {
      name: "Synthetic new folder",
      exact: true,
    }),
  ).toHaveAttribute("aria-current", "page");
  expect(state.projects[1].instructions).toBe("");
});

test("project read/edit Save and Cancel, compositions and curated assets, library add and remove", async ({
  page,
}) => {
  const state = await navigation(page);
  await page.goto("/#studio/project/1");
  await expect(
    page.getByText("Warm window light", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".project-style")).toContainText("Warm style");
  await expect(page.locator(".composition-grid .image-tile")).toHaveCount(1);
  await expect(page.locator(".asset-grid .image-tile")).toHaveCount(3);
  await expect(page.locator(".asset-grid")).toContainText("Retained chair");
  await expect(page.locator(".asset-grid")).toContainText("deleted");
  await expect(
    page.getByRole("textbox", { name: "Creative direction", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await sheet(page, "Edit project")
    .getByRole("textbox", { name: "Creative direction", exact: true })
    .fill("Discard this");
  await sheet(page, "Edit project")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  expect(state.projects[0].instructions).toBe("Warm window light");
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await sheet(page, "Edit project")
    .getByRole("textbox", { name: "Creative direction", exact: true })
    .fill("Cool morning light");
  state.fail = true;
  await sheet(page, "Edit project")
    .getByRole("button", { name: "Save", exact: true })
    .click();
  await expect(sheet(page, "Edit project").getByRole("alert")).toHaveText(
    "Synthetic save failure",
  );
  state.fail = false;
  await sheet(page, "Edit project")
    .getByRole("button", { name: "Save", exact: true })
    .click();
  await expect(sheet(page, "Edit project")).toHaveCount(0);
  await expect(
    page.getByText("Cool morning light", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Add from library", exact: true })
    .click();
  await sheet(page, "Add from library")
    .getByRole("searchbox", { name: "Search library" })
    .fill("lamp");
  await expect(
    sheet(page, "Add from library").locator(".asset-pick img"),
  ).toBeVisible();
  await sheet(page, "Add from library")
    .getByRole("button", { name: "Library lamp · Object/Vehicle" })
    .click();
  await sheet(page, "Add from library")
    .getByRole("button", { name: "Cancel", exact: true })
    .click();
  await expect(page.locator(".asset-grid .image-tile")).toHaveCount(4);
  await page
    .locator(".asset-grid .image-tile")
    .filter({ hasText: "Library lamp" })
    .getByRole("button", { name: "Remove from project" })
    .click();
  await expect(page.locator(".asset-grid .image-tile")).toHaveCount(3);
  await page
    .getByRole("button", { name: "New composition", exact: true })
    .click();
  await expect(
    sheet(page, "New composition").getByRole("combobox", {
      name: "Project",
      exact: true,
    }),
  ).toHaveValue("1");
  await sheet(page, "New composition")
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("New opening");
  await sheet(page, "New composition")
    .getByRole("button", { name: "Create composition", exact: true })
    .click();
  await expect(page).toHaveURL(/#composition\/4\/frame\/40$/);
  expect(state.posts[0].project_id).toBe(1);
});

test("workspace picker puts project assets first and standalone uses the whole library", async ({
  page,
}) => {
  const state = await navigation(page);
  await page.goto("/#composition/1/frame/10");
  await expect(
    sidebar(page).getByRole("link", {
      name: "Synthetic editorial",
      exact: true,
    }),
  ).toHaveAttribute("aria-current", "page");
  await page.getByRole("button", { name: "Add asset", exact: true }).click();
  const groups = page.locator(".asset-picker .picker-group");
  await expect(groups.first().getByRole("heading")).toHaveText(
    "Synthetic editorial",
  );
  await expect(groups.first()).toContainText("Project person");
  await expect(groups.first()).not.toContainText("Library lamp");
  await expect(groups.last().getByRole("heading")).toHaveText("All assets");
  await expect(groups.last()).toContainText("Library lamp");
  await page
    .getByRole("button", { name: "Library lamp · Object/Vehicle" })
    .click();
  expect(state.members[1]).toContain(1);
  await page.goto("/#composition/2/frame/20");
  await page.getByRole("button", { name: "Add asset", exact: true }).click();
  await expect(groups).toHaveCount(1);
  await expect(groups.first().getByRole("heading")).toHaveText("All assets");
  await expect(groups.first().getByRole("button", { name: / · / })).toHaveCount(
    2,
  );
});

test("legacy routes redirect to Studio and curated project views", async ({
  page,
}) => {
  await navigation(page);
  for (const [old, current] of [
    ["projects", "studio"],
    ["compositions", "studio"],
    ["project/1", "studio/project/1"],
    ["assets?used_by_project=1", "studio/project/1"],
  ]) {
    await page.goto(`/#${old}`);
    await expect(page).toHaveURL(new RegExp(`#${current}$`));
    await expect(
      page.getByRole("button", { name: "New composition", exact: true }),
    ).toBeVisible();
  }
});
