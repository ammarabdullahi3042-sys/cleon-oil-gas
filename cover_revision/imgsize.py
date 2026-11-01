from PIL import Image
from pathlib import Path
p=Path('cover_revision/cover-idml-01.png'); im=Image.open(p); print(im.size)
