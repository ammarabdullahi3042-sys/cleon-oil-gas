from PIL import Image
im=Image.open('cover_revision/dark-preview-01.png').convert('RGB')
for p in [(60,60),(200,60),(65,200),(60,1055),(80,1150),(500,100),(100,220)]: print(p,im.getpixel(p))
