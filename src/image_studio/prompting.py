"""Fixed prompt templates and ordered immutable reference snapshots."""


def assemble(project, composition, selections, variant):
    parts = [project["instructions"], composition["scene"]]
    references = []
    for asset, selection, images in selections:
        numbers = []
        for image in images:
            if (
                image["approved"]
                and not image["rejected"]
                and image["id"] not in selection["deselected_images"]
            ):
                numbers.append(str(len(references) + 1))
                references.append(reference(asset, selection["role"], image))
        parts.append(
            f"{selection['role']}: {asset['name']} — {asset['description']}"
            + (
                f" (reference images {', '.join(numbers)})"
                if numbers
                else " (no reference images)"
            )
        )
    parts.append(variant["instructions"])
    return {
        "prompt": "\n\n".join(p for p in parts if p.strip()),
        "references": references,
    }


def reference(asset, role, image):
    return {
        "hash": image["hash"],
        "asset_id": asset["id"],
        "role": role,
        "asset_name": asset["name"],
        "description": asset["description"],
        "type_tag": asset["type_tag"],
        "media_type": image["media_type"],
    }


def reference_view(asset, images):
    details = ": ".join(
        p for p in [asset["name"], asset["type_tag"], asset["description"]] if p
    )
    return {
        "prompt": (
            f"Create a clean reference view of {details}.\n"
            "Plain light background; the whole item in view."
        ),
        "references": [
            reference(asset, "reference subject", i)
            for i in images
            if i["source"] == "uploaded"
        ],
    }
