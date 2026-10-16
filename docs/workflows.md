# Workflows

## Assets and projects

Assets are global reusable references. Each has a name and type (person, garment/product, object/vehicle, environment, style, or other), an optional label, a description, and preservation instructions. Uploaded images are retained as originals. Approving an image makes it a canonical reference; rejecting hides it from normal views without removing its attachment or file. Generated reference candidates can also be reviewed. Deleted assets are soft-deleted and remain in history.

Projects are optional containers for creative direction and curated asset navigation. Assets may belong to multiple projects. Removing a project membership does not remove the asset or its stored files, and does not change a composition's pack.

## Compositions and storyboards

A composition belongs to an optional project and is either a single image or a storyboard. It has a brief, shared asset pack, and optional style choice. A single has one live frame. Storyboards have ordered live frames, each with a name, instructions and optional reference overrides. Reordering and hiding frames preserves their records and history. A storyboard can return to single form only when one live frame remains.

Frames may use the previous frame's final as an ordered reference, allowing a sequence to carry characters, setting and lighting forward. Sequence runs support the full storyboard, the next frame, or the rest of the sequence. A sequence can be asked to stop after its current frame.

## Generate, compare and review

Choose one to three models and one to four outputs per model. Shared content is assembled from project creative direction where present, the composition brief, style, asset roles and descriptions, preservation rules, and frame instructions. The endpoint's model capability profile determines supported prompt family, reference limits, formats, quality/resolution choices and advanced request fields. Prompts can be edited independently per model.

Each submitted run keeps its settings and exact input snapshot. Results appear in model columns; a model failure does not discard successful outputs from other models. Retry is available for failed generations and retains the original snapshot. Outputs can be rated, annotated and selected as a frame final. Technical details expose the sent prompt, settings, request fields and snapshot. Asset reference generation uses uploaded photos and supports the same candidate review.

## Export

Asset and composition exports are streamed ZIP files. Composition packages include retained frame information; sequence exports include final images and identify frames without finals. Export requests do not create files in storage or update records. See [data and formats](data-and-formats.md) for package contents and versions.
