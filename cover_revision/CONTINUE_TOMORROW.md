# CLEON business plan — resume tomorrow

Current files are in this folder:
- `CLEON_Business_Plan_Dark.pdf` — dark tables updated to muted slate rows, white text, and subtle borders matching the user’s reference. 13 pages; rendered page 11 checked.
- `CLEON_Business_Plan_Dark.idml` and `CLEON_Business_Plan_White.idml` — restored the missing `<?aid ...?>` processing instruction in `designmap.xml`; package XML parses and ZIP structure validates.
- `table_previews/Dark-slate-11.png` — preview of the revised dark table style.

Next step: have the user retry the repaired Dark IDML in InDesign 2022. It has not been tested in InDesign 2022 yet. If it still fails, continue diagnosing the IDML structure; do not repeat the DOMVersion-only downgrade in `indesign_2022/`.
