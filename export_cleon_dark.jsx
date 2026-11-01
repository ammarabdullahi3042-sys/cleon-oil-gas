app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
var src = File("C:/Users/ammar/Documents/Codex/2026-10-09/ri/outputs/CLEON_Business_Plan_Dark.idml");
var out = File("C:/Users/ammar/Documents/Codex/2026-10-09/ri/outputs/CLEON_Business_Plan_Dark.pdf");
var doc = app.open(src, false);
var n = doc.pages.length;
doc.exportFile(ExportFormat.PDF_TYPE, out, false, app.pdfExportPresets.itemByName("[High Quality Print]"));
doc.close(SaveOptions.NO);
app.quit();
n;
