"""Deterministic per-profile rendering, validated settings and request fields."""

import re
from decimal import Decimal

from werkzeug.exceptions import BadRequest


def render(content, references, info):
    family = info.get("prompt_family")
    indexed = list(enumerate(references, 1))
    if family == "gemini":
        indexed.sort(key=lambda pair: pair[1].get("type") != "person")
    refs = [r for _, r in indexed]
    if family not in ("openai", "gemini"):
        return content, refs
    numbers = {old: new for new, (old, _) in enumerate(indexed, 1)}
    content = re.sub(
        r"\(reference images ([0-9]+(?:, ?[0-9]+)*)\)",
        lambda m: (
            "(reference images "
            + ", ".join(str(numbers.get(int(n), int(n))) for n in m[1].split(","))
            + ")"
        ),
        content,
    )
    legend = "\n".join(
        f"Image {i}: {r['asset_name']}, {r['role']}, {r.get('type', 'other')}"
        for i, r in enumerate(refs, 1)
    )
    parts = [legend, content] if family == "openai" else [content, legend]
    return "\n\n".join(p for p in parts if p), refs


def formats(info):
    if "sizes" in info:
        return list(dict.fromkeys(s["aspect_ratio"] for s in info["sizes"]))
    return list(info.get("aspect_ratios", {}).get("values", []))


def options(info, ratio):
    if "sizes" in info:
        return {
            s["value"]: s["price"]
            for s in info["sizes"]
            if s["aspect_ratio"] == ratio and s.get("price") is not None
        }
    spec = info.get("qualities") or info.get("resolutions")
    prices = info.get("price_per_image", {})
    return {v: prices[v] for v in spec["values"] if v in prices} if spec else prices


def settings(info, supplied, ratio=None):
    if not isinstance(supplied, dict) or supplied.keys() - {
        "format",
        "quality",
        "advanced",
    }:
        raise BadRequest("settings must contain format, quality and advanced only")
    ratios = formats(info)
    ratio = (
        ratio
        or supplied.get("format")
        or ("1:1" if "1:1" in ratios else next(iter(ratios), None))
    )
    if ratio is not None and not isinstance(ratio, str):
        raise BadRequest("format must be text")
    if ratios and ratio not in ratios:
        raise BadRequest(f"Unsupported format {ratio}")
    if supplied.get("format", ratio) != ratio:
        raise BadRequest("Every model must use the run format")
    prices = options(info, ratio)
    if not prices:
        raise BadRequest("No priced quality or resolution for this format")
    quality = supplied.get("quality", min(prices, key=prices.get))
    if not isinstance(quality, str) or quality not in prices:
        raise BadRequest("Choose a priced quality or resolution")
    advanced = supplied.get("advanced", {})
    specs = {s["name"]: s for s in info.get("advanced", [])}
    if not isinstance(advanced, dict) or advanced.keys() - specs.keys():
        raise BadRequest("Unknown advanced setting")
    validated = {}
    for name, spec in specs.items():
        value = advanced.get(name, spec["default"])
        valid_type = (
            type(value) is int
            if spec.get("type") == "integer"
            else isinstance(value, str)
        )
        if (
            not valid_type
            or ("values" in spec and value not in spec["values"])
            or ("range" in spec and not spec["range"][0] <= value <= spec["range"][1])
        ):
            raise BadRequest(f"Invalid advanced value for {name}")
        validated[name] = value
    return {"format": ratio, "quality": quality, "advanced": validated}


def request_fields(model, prompt, info, selected, *, multipart=True):
    chat = info.get("endpoint") == "chat/completions"
    fields = (
        {
            "model": model,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            ],
            "modalities": ["text", "image"],
        }
        if chat
        else {"model": model, "prompt": prompt, "n": 1, "response_format": "b64_json"}
    )

    def put(field, value):
        if not chat and "." in field:
            raise BadRequest("Multipart profile fields must be plain names")
        target = fields
        parts = field.split(".")
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value

    if "sizes" in info:
        put("size", selected["quality"])
    elif "aspect_ratios" in info:
        spec = info["aspect_ratios"]
        values = spec["values"]
        put(
            spec["field"],
            values[selected["format"]]
            if isinstance(values, dict)
            else selected["format"],
        )
    spec = info.get("qualities") or info.get("resolutions")
    if spec:
        put(spec["field"], selected["quality"])
    for spec in info.get("advanced", []):
        put(spec.get("field", spec["name"]), selected["advanced"][spec["name"]])
    return fields if chat or not multipart else {k: str(v) for k, v in fields.items()}


def snapshot(model, content, refs, info, count, supplied=None, prompt=None, ratio=None):
    shared_refs = refs
    rendered, refs = render(content, refs, info)
    sent = rendered if prompt is None else prompt
    if not isinstance(sent, str) or not sent.strip():
        raise BadRequest("prompt must be nonempty text")
    limits = {"references": (len(refs), info["max_references"])}
    for slot, limit in info.get("reference_slots", {}).items():
        actual = sum((r.get("type") == "person") == (slot == "character") for r in refs)
        limits[slot] = (actual, limit)
    if "max_prompt_chars" in info:
        limits["prompt characters"] = (len(sent), info["max_prompt_chars"])
    for slot, (actual, limit) in limits.items():
        if actual > limit:
            raise BadRequest(
                f"{model}: selected {actual} {slot}; accepts at most {limit}. "
                "Adjust your selection."
            )
    selected = settings(info, {} if supplied is None else supplied, ratio)
    price = Decimal(str(options(info, selected["format"])[selected["quality"]]))
    price += len(refs) * Decimal(str(info.get("price_per_reference", 0)))
    return {
        "shared_references": shared_refs,
        "prompt_family": info.get("prompt_family"),
        "rendered_prompt": rendered,
        "assembled_prompt": content,
        "prompt": sent,
        "edited": sent != rendered,
        "references": refs,
        "settings": selected,
        "request_fields": request_fields(
            model, sent, info, selected, multipart=bool(refs)
        ),
        "estimated_cost": float(count * price),
    }
