import zipfile
z=zipfile.ZipFile('cover_revision/CLEON_Business_Plan_Dark.idml'); print([n for n in z.namelist() if n.lower().endswith(('.png','.jpg','.jpeg'))])
