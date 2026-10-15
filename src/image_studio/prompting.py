"""Fixed prompt templates and ordered immutable reference snapshots."""

from image_studio.api import ASSET_TYPES


def chosen_images(images, selection, variant):
    """References first, then explicitly selected unapproved Originals."""
    excluded = set(selection.get("deselected_images", [])) | set(
        variant.get("deselected_images", [])
    )
    originals = set(selection.get("selected_originals", [])) | set(
        variant.get("selected_originals", [])
    )
    refs = [i for i in images if i["approved"] and not i["rejected"]]
    extra = [
        i
        for i in images
        if i["source"] == "uploaded"
        and not i["approved"]
        and not i["rejected"]
        and i["id"] in originals
    ]
    return [i for i in refs + extra if i["id"] not in excluded]


def assemble(project, composition, selections, variant, previous=None):
    parts = [
        project["instructions"] if project else "",
        composition["brief"],
    ]
    references = [previous] if previous else []
    lines = []
    for asset, selection, images in selections:
        numbers = []
        for image in chosen_images(images, selection, variant):
            numbers.append(str(len(references) + 1))
            references.append(reference(asset, selection["role"], image))
        description = (
            f" — {asset['description']}" if asset["description"].strip() else ""
        )
        keep = (
            f"\nKeep: {asset['preserve']}" if asset.get("preserve", "").strip() else ""
        )
        label = ASSET_TYPES[asset.get("type", "other")]
        line = (
            (
                f"Style: {asset['name']}"
                if selection.get("style")
                else f"{selection['role']}: {asset['name']} ({label})"
            )
            + description
            + keep
            + (
                f" (reference images {', '.join(numbers)})"
                if numbers
                else " (no reference images)"
            )
        )
        if selection.get("style"):
            parts.append(line)
        else:
            lines.append(line)
    parts.extend(lines)
    if composition.get("kind") != "single":
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
        "type": asset.get("type", "other"),
        "preserve": asset.get("preserve", ""),
        "type_tag": asset["type_tag"],
        "media_type": image["media_type"],
    }


def reference_view(asset, images):
    details = ": ".join(
        p
        for p in [
            asset["name"],
            ASSET_TYPES[asset.get("type", "other")],
            asset["type_tag"],
            asset["description"],
        ]
        if p
    )
    keep = f"\nkeep: {asset['preserve']}" if asset.get("preserve", "").strip() else ""
    return {
        "prompt": (
            f"Create a clean reference view of {details}.\n"
            "Plain light background; the whole item in view." + keep
        ),
        "references": [
            reference(asset, "reference subject", i)
            for i in images
            if i["source"] == "uploaded"
        ],
    }
