from PIL import Image,ImageFilter
import numpy as np
im=Image.open('cover_revision/extracted0.png').convert('RGB'); a=np.array(im).astype(np.float32); R,G,B=a[:,:,0],a[:,:,1],a[:,:,2]
mask=np.zeros(a.shape[:2],bool)
r=(R[1380:1515,150:370]>165)&(G[1380:1515,150:370]<90)&(B[1380:1515,150:370]<105)&((R[1380:1515,150:370]-G[1380:1515,150:370])>95); mask[1380:1515,150:370]=r
r=(R[1410:1515,350:1100]>185)&(G[1410:1515,350:1100]>185)&(B[1410:1515,350:1100]>175)&((np.maximum(np.maximum(R[1410:1515,350:1100],G[1410:1515,350:1100]),B[1410:1515,350:1100])-np.minimum(np.minimum(R[1410:1515,350:1100],G[1410:1515,350:1100]),B[1410:1515,350:1100]))<55); mask[1410:1515,350:1100]=r
mask=np.array(Image.fromarray(mask.astype('uint8')*255).filter(ImageFilter.MaxFilter(3)))>0
out=a.copy(); known=~mask
for _ in range(250):
  sums=np.zeros_like(out); cnt=np.zeros(mask.shape,dtype=np.float32)
  for dy,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
   sh=np.roll(np.roll(out,dy,axis=0),dx,axis=1)
   km=np.roll(np.roll(known,dy,axis=0),dx,axis=1)
   sums += sh*km[:,:,None]; cnt += km
  upd=mask & (cnt>0); out[upd]=sums[upd]/cnt[upd,None]; known[upd]=True
# Keep only the designated text area masked.
Image.fromarray(np.clip(out,0,255).astype('uint8')).save('cover_revision/cover-clean.png')
