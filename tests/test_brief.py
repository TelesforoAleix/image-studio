"""Brief contracts and the Postgres U3 migration proof."""

from alembic import command
from alembic.config import Config
from test_api import client as postgres_client
from test_portability import unpack

from image_studio.prompting import assemble
from scripts.check_brief_migration import main as migration_proof

client = postgres_client


def test_u3_upgrade_twice_downgrade_and_reupgrade(client):
    command.downgrade(Config("alembic.ini"), "0009")
    migration_proof()


def test_template_brief_style_assets_and_storyboard_frame_order():
    style = {"id": 1, "name": "Ink", "type": "style", "description": "", "type_tag": ""}
    subject = {**style, "id": 2, "name": "Model", "type": "person"}
    selections = [
        (style, {"style": True, "role": "Style"}, []),
        (subject, {"role": "the model"}, []),
    ]
    composition = {"brief": "Synthetic brief", "kind": "storyboard"}
    frame = {"instructions": "Synthetic action"}
    expected = (
        "Project\n\nSynthetic brief\n\nStyle: Ink (no reference images)\n\n"
        "the model: Model (Person) (no reference images)"
    )
    assert assemble({"instructions": "Project"}, composition, selections, frame)[
        "prompt"
    ] == (expected + "\n\nSynthetic action")
    assert (
        assemble(
            {"instructions": "Project"},
            {**composition, "kind": "single"},
            selections,
            frame,
        )["prompt"]
        == expected
    )


def test_brief_api_preview_export(client):
    c, _, _ = client
    comp = c.post(
        "/api/compositions",
        json={"name": "Synthetic", "kind": "single", "brief": "Synthetic brief"},
    ).json
    path = f"/api/compositions/{comp['id']}"
    frame = comp["variants"][0]["id"]
    assert comp["brief"] == "Synthetic brief"
    assert "scene" not in comp and "direction" not in comp
    assert c.get(f"/api/variants/{frame}/preview").json["prompt"] == comp["brief"]
    assert (
        c.post(
            f"/api/variants/{frame}/preview",
            json={"brief": "Draft", "instructions": "Hidden"},
        ).json["prompt"]
        == "Draft"
    )
    assert c.get(path).json == comp  # preview never saves the draft
    assert c.patch(path, json={"brief": "Updated"}).json["brief"] == "Updated"
    package = unpack(c.get(path + "/export.zip").data)
    assert package["format_version"] == 5
    assert package["composition"]["brief"] == "Updated"
    assert "scene" not in package["composition"]
    assert "direction" not in package["composition"]
    for old in ["scene", "direction"]:
        assert c.patch(path, json={old: "Legacy"}).status_code == 400
