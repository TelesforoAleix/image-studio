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

## Navigation and prompt order

The interface routes are `#studio`, `#studio/none`, `#studio/project/<id>`,
`#assets`, `#assets/<type>`, `#asset/<id>`,
`#composition/<id>/frame/<frame-id>`, and `#storage`. `#projects` and
`#compositions` redirect to Studio; `#project/<id>` and
`#assets?used_by_project=<id>` redirect to the curated project view; `#library`
redirects to Assets and `#frame/<id>` to its composition workspace.
`#composition/<id>` selects the first live frame. Legacy `setup`, `generate`,
and `history` frame suffixes resolve to that workspace. Output links open the
viewer over the current page; browser Back closes it.

Prompt content has a fixed order: project creative direction, composition brief,
optional Style line, one line per subject, then storyboard frame instructions.
Empty sections are omitted. Subject lines contain role, name, type, description,
optional `Keep: <preserve>`, then ordered reference numbers. Style lines use the
same structure. Reference views use asset type and `keep: <preserve>` and send
the asset's uploaded originals. For `openai` prompt family, numbered image
legends precede content. `gemini` places content first and stably orders Person
references before other types, remapping legend numbers. Unknown prompt families
keep shared text and reference order. References are never silently dropped;
limits reject a run before records or jobs are inserted.

For chained storyboards, every later frame uses the previous live frame's final,
or the first output of its latest finished run when no final is selected. Runs
still waiting or failed do not provide a fallback. The resolved reference is
first and is pinned with its source in the generation snapshot. **Use the previous
frame** is on by default and can be disabled per frame. Singles and first frames
have no such reference. Sequence modes are full, next, and rest; rest resumes at
the failed frame when applicable. A sequence captures settings at start, queues
each frame in order, and stop takes effect after the current frame's models
finish.

## Keyboard controls

| Key | Output viewer |
| --- | --- |
| Left / Right | Previous / next output in run order |
| Up / Down | Older / newer run of the same frame |
| G / N | Set Good / Not good; repeat to clear |
| F | Mark focused completed composition output final |
| Enter | Open detailed feedback |
| C | Compare two or three outputs |
| Esc | Cancel feedback, leave compare, then close viewer |

In the asset page, focus a generated candidate and press **A** to approve or **R**
to reject. These controls are disabled while typing in form fields. Asset review
sections are To review, References, Originals, then optionally Rejected.
